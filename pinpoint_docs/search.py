import math
import re
from collections import Counter, defaultdict
from functools import cache

import chromadb

from pinpoint_docs.index import COLLECTION, DB, embed, load_chunks

TOKEN = re.compile(r"[a-z0-9_]+")


def tokenize(text):
    return TOKEN.findall(text.lower())


class BM25:
    def __init__(self, texts, k1=1.5, b=0.75):
        self.k1, self.b = k1, b
        self.lens = []
        self.postings = defaultdict(list)
        for i, text in enumerate(texts):
            counts = Counter(tokenize(text))
            self.lens.append(sum(counts.values()))
            for word, tf in counts.items():
                self.postings[word].append((i, tf))
        self.avg = sum(self.lens) / len(self.lens)
        n = len(self.lens)
        self.idf = {w: math.log(1 + (n - len(p) + 0.5) / (len(p) + 0.5)) for w, p in self.postings.items()}

    def rank(self, query, k=50):
        scores = defaultdict(float)
        for word in set(tokenize(query)):
            for i, tf in self.postings.get(word, []):
                norm = tf + self.k1 * (1 - self.b + self.b * self.lens[i] / self.avg)
                scores[i] += self.idf[word] * tf * (self.k1 + 1) / norm
        return sorted(scores, key=scores.get, reverse=True)[:k]


def rrf(rankings, k=60):
    scores = defaultdict(float)
    for ranking in rankings:
        for rank, item in enumerate(ranking):
            scores[item] += 1 / (k + rank + 1)
    return sorted(scores.items(), key=lambda pair: pair[1], reverse=True)


def mmr(query, vectors, k=5, weight=0.7):
    chosen, left = [], list(range(len(vectors)))
    while left and len(chosen) < k:
        def value(i):
            redundancy = max((float(vectors[i] @ vectors[j]) for j in chosen), default=0.0)
            return weight * float(query @ vectors[i]) - (1 - weight) * redundancy
        best = max(left, key=value)
        chosen.append(best)
        left.remove(best)
    return chosen


@cache
def load():
    chunks = load_chunks()
    bm25 = BM25([f"{c['title']}\n{c['text']}" for c in chunks])
    col = chromadb.PersistentClient(str(DB)).get_collection(COLLECTION)
    return {c["id"]: c for c in chunks}, [c["id"] for c in chunks], bm25, col


def embed_question(question):
    return embed([f"search_query: {question}"], num_gpu=0)[0]


def search(question, k=5, pool=50, vector=None):
    by_id, ids, bm25, col = load()
    lexical = [ids[i] for i in bm25.rank(question, pool)]
    vector = embed_question(question) if vector is None else vector
    semantic = col.query(query_embeddings=[vector], n_results=pool)["ids"][0]
    return [{**by_id[i], "score": round(score, 4)} for i, score in rrf([lexical, semantic])[:k]]
