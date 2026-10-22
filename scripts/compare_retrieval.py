import hashlib
import json
import re
import statistics
import sys
import time
from pathlib import Path

import numpy as np

from pinpoint_docs import chunk
from pinpoint_docs.index import BATCH, document, embed
from pinpoint_docs.search import BM25, mmr, rrf

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "data" / "eval_cache"
QUESTIONS = ROOT / "evals" / "questions.json"
TOP = 50
MMR_POOL = 20
WINDOW, STRIDE = 1200, 1000


def headings(max_chars):
    old, chunk.MAX_CHARS = chunk.MAX_CHARS, max_chars
    try:
        return chunk.build()
    finally:
        chunk.MAX_CHARS = old


def by_page():
    pages = {}
    for c in headings(10**9):
        pages.setdefault(c["page"], {"page": c["page"], "title": c["title"], "text": []})["text"].append(c["text"])
    return [{**p, "text": "\n\n".join(p["text"])} for p in pages.values()]


def fixed():
    out = []
    for p in by_page():
        for start in range(0, max(len(p["text"]) - WINDOW + STRIDE, 1), STRIDE):
            out.append({**p, "text": p["text"][start : start + WINDOW]})
    return out


STRATEGIES = {
    "whole page": by_page,
    "fixed 1200 chars": fixed,
    "headings, no cap": lambda: headings(10**9),
    "headings, cap 1500": lambda: headings(1500),
    "headings, cap 3000": lambda: headings(3000),
}


def embed_all(texts):
    key = hashlib.sha256("\x00".join(texts).encode()).hexdigest()[:16]
    path = CACHE / f"{key}.npy"
    if path.exists():
        return np.load(path), 0.0
    start = time.perf_counter()
    vectors = []
    for i in range(0, len(texts), BATCH):
        vectors += embed(texts[i : i + BATCH])
    seconds = time.perf_counter() - start
    CACHE.mkdir(exist_ok=True)
    np.save(path, np.array(vectors, dtype=np.float32))
    return np.load(path), seconds


def normalize(m):
    return m / np.linalg.norm(m, axis=1, keepdims=True)


def query_text(q, full):
    if not full:
        return q["title"]
    keep = re.findall(r"### (?:Example Code|Description)\n(.*?)(?=\n### |\Z)", q["question"], re.S)
    return q["title"] + "\n\n" + ("\n\n".join(keep) if keep else q["question"])


def score(ranking, chunks, gold, k_context=5):
    pages = [chunks[i]["page"] for i in ranking]
    first = next((r for r, p in enumerate(pages[:10]) if p in gold), None)
    return {
        "hit@1": first == 0,
        "hit@5": first is not None and first < 5,
        "mrr@10": 0 if first is None else 1 / (first + 1),
        "context": sum(len(chunks[i]["text"]) for i in ranking[:k_context]),
        "rank": first,
    }


def main():
    split = sys.argv[1] if len(sys.argv) > 1 else "dev"
    ids = set(json.loads((ROOT / "evals" / "split.json").read_text(encoding="utf-8"))[split])
    questions = [
        q
        for q in json.loads(QUESTIONS.read_text(encoding="utf-8"))["questions"]
        if q["tag"] == "docs" and q["id"] in ids
    ]
    queries = {full: [query_text(q, full) for q in questions] for full in (False, True)}
    query_vecs = {full: normalize(embed_all([f"search_query: {t}" for t in qs])[0]) for full, qs in queries.items()}

    rows = []
    for name, make in STRATEGIES.items():
        chunks = make()
        vecs, seconds = embed_all([document(c) for c in chunks])
        vecs = normalize(vecs)
        bm25 = BM25([f"{c['title']}\n{c['text']}" for c in chunks])
        for full in (False, True):
            results = {"bm25": [], "vector": [], "hybrid": [], "hybrid + MMR 0.7": [], "hybrid + MMR 0.5": []}
            for q, text, qv in zip(questions, queries[full], query_vecs[full], strict=True):
                gold = set(q["gold_pages"])
                lexical = bm25.rank(text, TOP)
                semantic = [int(i) for i in np.argsort(-(vecs @ qv))[:TOP]]
                fused = [i for i, _ in rrf([lexical, semantic])]
                rankings = [("bm25", lexical), ("vector", semantic), ("hybrid", fused)]
                for weight in (0.7, 0.5):
                    pool = fused[:MMR_POOL]
                    picked = [pool[i] for i in mmr(qv, vecs[pool], k=5, weight=weight)]
                    rankings.append((f"hybrid + MMR {weight}", picked + [i for i in fused if i not in picked]))
                for method, ranking in rankings:
                    results[method].append(score(ranking, chunks, gold))
            for method, scores in results.items():
                rows.append(
                    {
                        "chunking": name,
                        "chunks": len(chunks),
                        "embed_seconds": round(seconds, 1),
                        "query": "title + body" if full else "title only",
                        "search": method,
                        **{m: round(statistics.mean(s[m] for s in scores), 3) for m in ("hit@1", "hit@5", "mrr@10")},
                        "context_chars": round(statistics.median(s["context"] for s in scores)),
                        "ranks": [s["rank"] for s in scores],
                    }
                )
        print(f"done: {name} ({len(chunks)} chunks, embedded in {seconds:.0f}s)", flush=True)

    out = ROOT / "evals" / f"retrieval_results_{split}.json"
    out.write_text(json.dumps({"split": split, "questions": len(questions), "rows": rows}, indent=1), encoding="utf-8")
    print(f"\n{len(questions)} questions -> {out}\n")
    print("| chunking | query | search | hit@1 | hit@5 | MRR@10 | context chars (top 5) |")
    print("|---|---|---|---|---|---|---|")
    for r in rows:
        print(
            f"| {r['chunking']} | {r['query']} | {r['search']} | {r['hit@1']:.2f} | {r['hit@5']:.2f} | {r['mrr@10']:.2f} | {r['context_chars']} |"
        )


if __name__ == "__main__":
    main()
