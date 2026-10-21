import sys
import time

from pinpoint_docs.answer import excerpts, is_answerable
from pinpoint_docs.search import search
from scripts.compare_retrieval import query_text
from scripts.run_eval import load_questions, sample


def main():
    seed = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    questions = load_questions()
    used = set() if seed == 0 else {q["id"] for q in sample(questions)}
    rows = []
    for n, q in enumerate(sample(questions, seed=seed, exclude=used), 1):
        text = query_text(q, full=True)
        hits = search(text)
        found = any(c["page"] in q["gold_pages"] for c in hits)
        start = time.perf_counter()
        yes, _ = is_answerable(text, excerpts(hits))
        rows.append((q["tag"], found, yes))
        print(f"{n}/40 {q['tag']:<13} found gold: {found!s:<5} says: {'YES' if yes else 'NO '} {time.perf_counter() - start:4.1f}s  #{q['id']} {q['title'][:50]}", flush=True)

    found_docs = [yes for tag, found, yes in rows if tag == "docs" and found]
    missed_docs = [yes for tag, found, yes in rows if tag == "docs" and not found]
    other = [yes for tag, _, yes in rows if tag != "docs"]
    print(f"\ndocs, search found gold: YES {sum(found_docs)}/{len(found_docs)}")
    print(f"docs, search missed:     NO {len(missed_docs) - sum(missed_docs)}/{len(missed_docs)}")
    print(f"non-docs:                NO {len(other) - sum(other)}/{len(other)}")


if __name__ == "__main__":
    main()
