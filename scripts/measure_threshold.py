import json
import statistics
from pathlib import Path

import chromadb

from pinpoint_docs.index import COLLECTION, DB
from scripts.compare_retrieval import embed_all, query_text

ROOT = Path(__file__).resolve().parent.parent


def main():
    questions = [
        q
        for q in json.loads((ROOT / "evals" / "questions.json").read_text(encoding="utf-8"))["questions"]
        if q["tag"] != "skip"
    ]
    vectors, _ = embed_all([f"search_query: {query_text(q, True)}" for q in questions])
    col = chromadb.PersistentClient(str(DB)).get_collection(COLLECTION)
    nearest = col.query(query_embeddings=vectors.tolist(), n_results=1)["distances"]
    docs = [d[0] for q, d in zip(questions, nearest, strict=True) if q["tag"] == "docs"]
    other = [d[0] for q, d in zip(questions, nearest, strict=True) if q["tag"] != "docs"]

    print(
        f"closest-chunk distance, median: docs {statistics.median(docs):.3f} ({len(docs)}), not docs {statistics.median(other):.3f} ({len(other)})\n"
    )
    print("| cutoff | docs questions still answered | non-docs questions stopped |")
    print("|---|---|---|")
    for cut in [x / 100 for x in range(20, 52, 2)]:
        kept = sum(d <= cut for d in docs) / len(docs)
        stopped = sum(d > cut for d in other) / len(other)
        print(f"| {cut:.2f} | {kept:.0%} | {stopped:.0%} |")


if __name__ == "__main__":
    main()
