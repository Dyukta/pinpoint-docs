import re
import sys

from pinpoint_docs.search import search
from scripts.compare_retrieval import query_text
from scripts.run_eval import load_split

CODE = re.compile(r"```.*?```", re.S)


def main():
    name = sys.argv[1] if len(sys.argv) > 1 else "dev"
    docs = [q for q in load_split(name) if q["gold_pages"]]
    ranks = []
    for q in docs:
        text = query_text(q, full=True)
        hits = search(text, k=50)
        rank = next((n for n, h in enumerate(hits, 1) if h["page"] in q["gold_pages"]), None)
        ranks.append(rank)
        if rank and rank <= 3:
            continue
        code = sum(len(block) for block in CODE.findall(text))
        print(f"#{q['id']} rank {rank}, {len(text)} chars, {100 * code // len(text)}% code: {q['title'][:70]}")
        print(f"   gold: {q['gold_pages']}")
        print(f"   top3: {[h['page'] for h in hits[:3]]}")
    print()
    for k in (1, 3, 5, 10):
        print(f"hit@{k}: {sum(r is not None and r <= k for r in ranks)}/{len(docs)}")


if __name__ == "__main__":
    main()
