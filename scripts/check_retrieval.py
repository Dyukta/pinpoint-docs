import sys

from pinpoint_docs.index import load_chunks
from pinpoint_docs.search import BM25
from scripts.compare_retrieval import query_text
from scripts.run_eval import load_split

BAR = 17


def hits_at(k=3):
    chunks = load_chunks()
    bm25 = BM25([f"{c['title']}\n{c['text']}" for c in chunks])
    questions = [q for q in load_split("dev") if q["gold_pages"]]
    hits = sum(
        any(chunks[i]["page"] in q["gold_pages"] for i in bm25.rank(query_text(q, full=True), k)) for q in questions
    )
    return hits, len(questions)


def main():
    hits, total = hits_at()
    print(f"BM25 hit@3 on dev: {hits}/{total} (bar {BAR})")
    sys.exit(hits < BAR)


if __name__ == "__main__":
    main()
