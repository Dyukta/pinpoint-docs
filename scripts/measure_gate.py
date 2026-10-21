import json
import re
import sys
import time

from pinpoint_docs.answer import CHECK, CHECK_ASK, MODEL, chat, excerpts
from pinpoint_docs.search import search
from scripts.compare_retrieval import query_text
from scripts.run_eval import ROOT, load_split

PARTIAL_ASK = "Do these excerpts contain information that answers the question, fully or in part? Reply YES or NO."


def without_code(q):
    description = re.findall(r"### Description\n(.*?)(?=\n### |\Z)", q["question"], re.S)
    body = description[0] if description else re.sub(r"```.*?```", "", q["question"], flags=re.S)
    return q["title"] + "\n\n" + body.strip()


VARIANTS = {
    "current": (CHECK_ASK, lambda q: query_text(q, full=True)),
    "fully or in part": (PARTIAL_ASK, lambda q: query_text(q, full=True)),
    "no code": (CHECK_ASK, without_code),
}


def says_yes(question, context, ask):
    reply = chat(MODEL, CHECK, f"Question:\n{question}\n\nExcerpts:\n\n{context}\n\n{ask}", num_predict=3)
    return reply["message"]["content"].strip().upper().startswith("YES")


def main():
    name = sys.argv[1] if len(sys.argv) > 1 else "dev"
    rows = []
    for n, q in enumerate(load_split(name), 1):
        hits = search(query_text(q, full=True))
        found = any(c["page"] in q["gold_pages"] for c in hits)
        context = excerpts(hits)
        start = time.perf_counter()
        votes = {v: says_yes(make(q), context, ask) for v, (ask, make) in VARIANTS.items()}
        rows.append({"id": q["id"], "docs": bool(q["gold_pages"]), "found": found, **votes})
        print(f"{n}/{len(load_split(name))} {'docs' if q['gold_pages'] else 'other'} found={found!s:<5} " + " ".join(f"{v}={'Y' if y else 'N'}" for v, y in votes.items()) + f" {time.perf_counter() - start:.0f}s", flush=True)

    out = ROOT / "evals" / f"gate_{name}.json"
    out.write_text(json.dumps({"split": name, "rows": rows}, indent=1), encoding="utf-8")
    found = [r for r in rows if r["docs"] and r["found"]]
    missed = [r for r in rows if r["docs"] and not r["found"]]
    other = [r for r in rows if not r["docs"]]
    print(f"\n-> {out.name}\n{'variant':<18} found docs YES   missed docs NO   non-docs NO")
    for v in VARIANTS:
        print(f"{v:<18} {sum(r[v] for r in found):>3}/{len(found):<11} {sum(not r[v] for r in missed):>3}/{len(missed):<12} {sum(not r[v] for r in other):>3}/{len(other)}")


if __name__ == "__main__":
    main()
