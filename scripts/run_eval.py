import json
import random
import statistics
import sys
from collections import Counter
from pathlib import Path

from pinpoint_docs.answer import IDK, MODEL, answer
from pinpoint_docs.chunk import page_url
from scripts.compare_retrieval import query_text

ROOT = Path(__file__).resolve().parent.parent
PER_GROUP = 20


def load_questions():
    return json.loads((ROOT / "evals" / "questions.json").read_text(encoding="utf-8"))["questions"]


def sample(questions, n=PER_GROUP, seed=0, exclude=()):
    rng = random.Random(seed)
    docs = [q for q in questions if q["tag"] == "docs" and q["id"] not in exclude]
    other = [q for q in questions if q["tag"] in ("bug", "other-library") and q["id"] not in exclude]
    return rng.sample(docs, n) + rng.sample(other, n)


def grade(q, result):
    gold = q["gold_pages"]
    said_idk = result["answer"] == IDK
    if not gold:
        row = {"said_idk": said_idk, "pass": said_idk, "failure": None if said_idk else "answered_unanswerable"}
    else:
        found = any(i.split("#")[0] in gold for i in result["retrieved"])
        cited = bool({url.split("#")[0] for url in result["sources"]} & {page_url(p) for p in gold})
        ok = cited and not said_idk
        failure = None if ok else "search_missed_gold" if not found else "refused_with_gold" if said_idk else "cited_wrong_page"
        row = {"said_idk": said_idk, "search_found_gold": found, "cited_gold": cited, "pass": ok, "failure": failure}
    if result.get("error"):
        row |= {"pass": False, "failure": "error"}
    return row


def seconds(r):
    return sum(r[k] or 0 for k in ("search_seconds", "check_seconds", "answer_seconds"))


def run(questions, model, name):
    results = []
    for n, q in enumerate(questions, 1):
        result = answer(query_text(q, full=True), model=model, use_cache=False)
        row = {"id": q["id"], "title": q["title"], "tag": q["tag"], "gold_pages": q["gold_pages"], **grade(q, result), **result}
        results.append(row)
        print(f"{n}/{len(questions)} {'PASS' if row['pass'] else 'FAIL'} {q['tag']:<13} {'YES' if result['answerable'] else 'NO '} {seconds(row):>5.1f}s  #{q['id']} {q['title'][:60]}", flush=True)

    out = ROOT / "evals" / f"{name}_{model.replace(':', '-')}.json"
    out.write_text(json.dumps({"model": model, "results": results}, indent=1, ensure_ascii=False), encoding="utf-8")
    report(results)
    print(f"-> {out.name}")
    return results


def report(results):
    n = len(results)
    docs = [r for r in results if r["gold_pages"]]
    other = [r for r in results if not r["gold_pages"]]
    share = lambda rows, key: f"{sum(r[key] for r in rows)}/{len(rows)}"
    print()
    if docs:
        print(f"docs questions:     search found gold {share(docs, 'search_found_gold')}, cited gold {share(docs, 'cited_gold')}, wrongly said I don't know {share(docs, 'said_idk')}")
    if other:
        print(f"non-docs questions: correctly said I don't know {share(other, 'said_idk')}")
    print(f"passed {share(results, 'pass')}")
    print(f"failures: {dict(Counter(r['failure'] for r in results if r['failure']).most_common())}")

    ok = [r for r in results if not r.get("error")]
    total = [seconds(r) for r in ok]
    p95 = statistics.quantiles(total, n=20, method="inclusive")[-1] if len(total) > 1 else total[0]
    print(f"latency per question: p50 {statistics.median(total):.1f}s, p95 {p95:.1f}s")
    for step in ("search_seconds", "check_seconds", "answer_seconds"):
        values = [r[step] for r in ok if r[step] is not None]
        if values:
            print(f"  {step.removesuffix('_seconds')}: p50 {statistics.median(values):.1f}s")
    print(f"tokens per 1,000 questions: prompt {sum(r['prompt_tokens'] for r in results) / n * 1000:,.0f}, output {sum(r['output_tokens'] for r in results) / n * 1000:,.0f}")
    print(f"answered {n - sum(r['said_idk'] for r in results)}/{n}, said I don't know {sum(r['said_idk'] for r in results)}/{n}, errors {sum(bool(r.get('error')) for r in results)}/{n}")
    for tag in sorted({r["tag"] for r in results}):
        rows = [r for r in ok if r["tag"] == tag]
        print(f"  {tag:<13} passed {share(rows, 'pass')}, p50 {statistics.median(seconds(r) for r in rows):.1f}s")


def load_split(name):
    ids = json.loads((ROOT / "evals" / "split.json").read_text(encoding="utf-8"))[name]
    by_id = {q["id"]: q for q in load_questions()}
    return [by_id[i] for i in ids]


def main():
    name = sys.argv[1] if len(sys.argv) > 1 else "test"
    model = sys.argv[2] if len(sys.argv) > 2 else MODEL
    run(load_split(name), model, f"eval_{name}")


if __name__ == "__main__":
    main()
