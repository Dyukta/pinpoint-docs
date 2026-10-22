import json
import sys
import time

from pinpoint_docs.answer import MODEL, chat, search_again
from pinpoint_docs.search import search
from scripts.compare_retrieval import query_text
from scripts.run_eval import ROOT, load_split

K = 3
REWRITE = (
    "You turn a user's FastAPI question into a short search query for the FastAPI documentation. "
    "Use the words the docs would use: feature names, class and function names. "
    "Reply with only the query, at most 12 words."
)


def has_gold(hits, q):
    return any(h["page"] in q["gold_pages"] for h in hits)


def main():
    name = sys.argv[1] if len(sys.argv) > 1 else "dev"
    docs = [q for q in load_split(name) if q["gold_pages"]]
    rows = []
    for n, q in enumerate(docs, 1):
        text = query_text(q, full=True)
        start = time.perf_counter()
        reply = chat(MODEL, REWRITE, text, num_predict=30)
        seconds = time.perf_counter() - start
        query = reply["message"]["content"].strip().strip('"')
        before, after = has_gold(search(text, K), q), has_gold(search(query, K), q)
        tool_query, tool_reply = search_again(text, MODEL)
        tool_after = bool(tool_query) and has_gold(search(tool_query, K), q)
        rows.append(
            {
                "id": q["id"],
                "query": query,
                "before": before,
                "after": after,
                "seconds": round(seconds, 2),
                "tool_query": tool_query,
                "tool_text": tool_reply["message"].get("content", "")[:200],
                "tool_after": tool_after,
            }
        )
        mark = "FIXED" if after and not before else "LOST" if before and not after else ""
        tool = f"tool: {tool_query[:40]!r}" if tool_query else "tool: no call"
        print(
            f"{n}/{len(docs)} #{q['id']} {'Y' if before else 'N'}->{'Y' if after else 'N'} {mark:<5} {query[:50]:<50} {tool}"
        )

    out = ROOT / "evals" / f"rewrite_{name}.json"
    out.write_text(json.dumps({"split": name, "k": K, "rows": rows}, indent=1, ensure_ascii=False), encoding="utf-8")
    misses = [r for r in rows if not r["before"]]
    found = [r for r in rows if r["before"]]
    print(f"\n-> {out.name}")
    print(f"misses fixed by the rewritten query: {sum(r['after'] for r in misses)}/{len(misses)}")
    print(f"found pages the rewritten query would lose: {sum(not r['after'] for r in found)}/{len(found)}")
    print(f"rewrite call: median {sorted(r['seconds'] for r in rows)[len(rows) // 2]:.1f}s")
    print(f"tool calling: a valid search_docs call on {sum(bool(r['tool_query']) for r in rows)}/{len(rows)} questions")
    print(f"misses fixed by the tool call's query: {sum(r['tool_after'] for r in misses)}/{len(misses)}")


if __name__ == "__main__":
    main()
