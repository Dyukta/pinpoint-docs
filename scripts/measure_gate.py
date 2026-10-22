import json
import re
import sys
import time

from pinpoint_docs.answer import CHECK, CHECK_ASK, MODEL, chat, excerpts
from pinpoint_docs.search import search
from scripts.compare_retrieval import query_text
from scripts.run_eval import ROOT, load_split

K = 3
NAME_SYSTEM = "You check whether documentation excerpts answer a question. Reply with only an excerpt number or NONE."
NAME_ASK = "Which excerpt contains the answer to the question? Reply with only the excerpt number, or NONE."


def says_yes(reply, hits):
    return reply.strip().upper().startswith("YES")


def names_excerpt(reply, hits):
    number = re.search(r"\d+", reply)
    return bool(number) and 1 <= int(number[0]) <= len(hits)


VARIANTS = {
    "llama3.2 yes/no": (MODEL, CHECK, CHECK_ASK, says_yes),
    "llama3.2 name excerpt": (MODEL, NAME_SYSTEM, NAME_ASK, names_excerpt),
    "qwen2.5:3b yes/no": ("qwen2.5:3b", CHECK, CHECK_ASK, says_yes),
}


def main():
    name = sys.argv[1] if len(sys.argv) > 1 else "dev"
    peek = "peek" in sys.argv
    questions = load_split(name)
    rows = []
    for q in questions:
        text = query_text(q, full=True)
        hits = search(text, K)
        found = any(c["page"] in q["gold_pages"] for c in hits)
        rows.append({"id": q["id"], "docs": bool(q["gold_pages"]), "found": found, "text": text, "hits": hits})
    if peek:
        rows = [r for r in rows if r["found"]][:4] + [r for r in rows if not r["docs"]][:2]

    for variant, (model, system, ask, accepts) in VARIANTS.items():
        start = time.perf_counter()
        for n, row in enumerate(rows, 1):
            prompt = f"Question:\n{row['text']}\n\nExcerpts:\n\n{excerpts(row['hits'])}\n\n{ask}"
            reply = chat(model, system, prompt, num_predict=10)["message"]["content"]
            row[variant] = accepts(reply, row["hits"])
            row[f"{variant} reply"] = reply
            if peek:
                print(f"{variant:<24} #{row['id']} {'docs found' if row['docs'] else 'out of scope'}: {reply!r}")
            else:
                print(f"\r{variant}: {n}/{len(rows)}", end="", flush=True)
        print(f"  {time.perf_counter() - start:.0f}s")
    if peek:
        return

    out = ROOT / "evals" / f"gate_models_{name}.json"
    keep = ["id", "docs", "found", *VARIANTS, *(f"{v} reply" for v in VARIANTS)]
    out.write_text(json.dumps({"split": name, "k": K, "rows": [{k: r[k] for k in keep} for r in rows]}, indent=1))
    found = [r for r in rows if r["docs"] and r["found"]]
    missed = [r for r in rows if r["docs"] and not r["found"]]
    other = [r for r in rows if not r["docs"]]
    print(f"\n-> {out.name}\n{'variant':<24} found docs YES   missed docs NO   non-docs NO")
    for v in VARIANTS:
        yes_found = f"{sum(r[v] for r in found)}/{len(found)}"
        no_missed = f"{sum(not r[v] for r in missed)}/{len(missed)}"
        no_other = f"{sum(not r[v] for r in other)}/{len(other)}"
        print(f"{v:<24} {yes_found:<16} {no_missed:<16} {no_other}")


if __name__ == "__main__":
    main()
