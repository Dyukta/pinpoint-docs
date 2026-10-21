import json
import urllib.request
from pathlib import Path

import chromadb
from chromadb.errors import NotFoundError

ROOT = Path(__file__).resolve().parent.parent
CHUNKS = ROOT / "data" / "chunks.jsonl"
DB = ROOT / "data" / "chroma"
COLLECTION = "fastapi-0.150.0"
CACHE = "answer-cache"
OLLAMA = "http://localhost:11434"
EMBED_MODEL = "nomic-embed-text"
BATCH = 64


def ollama(path, payload):
    req = urllib.request.Request(
        f"{OLLAMA}{path}",
        json.dumps(payload).encode(),
        {"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as r:
        return json.load(r)


def embed(texts, **options):
    return ollama("/api/embed", {"model": EMBED_MODEL, "input": texts, "options": options})["embeddings"]


def document(chunk):
    return f"search_document: {chunk['title']}\n{chunk['text']}"


def load_chunks():
    with CHUNKS.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f]


def main():
    chunks = load_chunks()
    client = chromadb.PersistentClient(str(DB))
    for name in (COLLECTION, CACHE):
        try:
            client.delete_collection(name)
        except NotFoundError:
            pass
    col = client.create_collection(COLLECTION, configuration={"hnsw": {"space": "cosine"}})

    for i in range(0, len(chunks), BATCH):
        batch = chunks[i:i + BATCH]
        col.add(
            ids=[c["id"] for c in batch],
            documents=[c["text"] for c in batch],
            metadatas=[{k: c[k] for k in ("page", "title", "section", "url")} for c in batch],
            embeddings=embed([document(c) for c in batch]),
        )
        print(f"embedded {i + len(batch)}/{len(chunks)}", end="\r")
    print(f"\n{col.count()} chunks stored in {DB}")

    question = "How do I declare a request body?"
    hits = col.query(query_embeddings=embed([f"search_query: {question}"]), n_results=3)
    print(f"\n{question}")
    for meta, dist in zip(hits["metadatas"][0], hits["distances"][0]):
        print(f"  {dist:.3f}  {meta['page']}  ({meta['section']})")


if __name__ == "__main__":
    main()
