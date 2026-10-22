import json
import random
import statistics
import sys
from collections import Counter
from pathlib import Path

from pinpoint_docs.answer import IDK, MODEL, answer
from pinpoint_docs.chunk import page_url
from pinpoint_docs.stats import STEPS, percentile, seconds
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
        failure = (
            None
            if ok
            else "search_missed_gold"
            if not found
            else "refused_with_gold"
            if said_idk
            else "cited_wrong_page"
        )
        row = {"said_idk": said_idk, "search_found_gold": found, "cited_gold": cited, "pass": ok, "failure": failure}
    if result.get("error"):
        row |= {"pass": False, "failure": "error"}
    return row


def run(questions, model, name, check=True, k=3, agent=False):
    results = []
    for n, q in enumerate(questions, 1):
        result = answer(query_text(q, full=True), k=k, model=model, use_cache=False, check=check, agent=agent)
        row = {
            "id": q["id"],
            "title": q["title"],
            "tag": q["tag"],
            "gold_pages": q["gold_pages"],
            **grade(q, result),
            **result,
        }
        results.append(row)
        print(
            f"{n}/{len(questions)} {'PASS' if row['pass'] else 'FAIL'} {q['tag']:<13} {'YES' if result['answerable'] else 'NO '} {seconds(row):>5.1f}s  #{q['id']} {q['title'][:60]}",
            flush=True,
        )

    out = ROOT / "evals" / f"{name}_{model.replace(':', '-')}.json"
    out.write_text(json.dumps({"model": model, "results": results}, indent=1, ensure_ascii=False), encoding="utf-8")
    report(results)
    print(f"-> {out.name}")
    return results


def share(rows, key):
    return f"{sum(r[key] for r in rows)}/{len(rows)}"


def report(results):
    n = len(results)
    docs = [r for r in results if r["gold_pages"]]
    other = [r for r in results if not r["gold_pages"]]
    print()
    if docs:
        print(
            f"docs questions:     search found gold {share(docs, 'search_found_gold')}, cited gold {share(docs, 'cited_gold')}, wrongly said I don't know {share(docs, 'said_idk')}"
        )
    if other:
        print(f"non-docs questions: correctly said I don't know {share(other, 'said_idk')}")
    print(f"passed {share(results, 'pass')}")
    print(f"failures: {dict(Counter(r['failure'] for r in results if r['failure']).most_common())}")

    ok = [r for r in results if not r.get("error")]
    total = [seconds(r) for r in ok]
    print(f"latency per question: p50 {percentile(total, 50):.1f}s, p95 {percentile(total, 95):.1f}s")
    for step in STEPS:
        values = [r[step] for r in ok if r.get(step) is not None]
        if values:
            print(f"  {step.removesuffix('_seconds')}: p50 {statistics.median(values):.1f}s")
    for step in ("check", "agent", "answer"):
        calls = [c for r in ok for c in r.get("calls", []) if c["step"] == step]
        if calls:
            p50 = {key: statistics.median(c[key] for c in calls) for key in calls[0] if key != "step"}
            print(
                f"  {step} call: read {p50['read_seconds']:.1f}s for {p50['prompt_tokens']:.0f} tokens, "
                f"write {p50['write_seconds']:.1f}s for {p50['output_tokens']:.0f} tokens, load {p50['load_seconds']:.1f}s"
            )
    print(
        f"tokens per 1,000 questions: prompt {sum(r['prompt_tokens'] for r in results) / n * 1000:,.0f}, output {sum(r['output_tokens'] for r in results) / n * 1000:,.0f}"
    )
    print(
        f"answered {n - sum(r['said_idk'] for r in results)}/{n}, said I don't know {sum(r['said_idk'] for r in results)}/{n}, errors {sum(bool(r.get('error')) for r in results)}/{n}"
    )
    for tag in sorted({r["tag"] for r in results}):
        rows = [r for r in ok if r["tag"] == tag]
        print(f"  {tag:<13} passed {share(rows, 'pass')}, p50 {statistics.median(seconds(r) for r in rows):.1f}s")


def load_split(name):
    ids = json.loads((ROOT / "evals" / "split.json").read_text(encoding="utf-8"))[name]
    by_id = {q["id"]: q for q in load_questions()}
    return [by_id[i] for i in ids]


def fresh_sample(n=40, seed=None):
    seed = random.randrange(10_000) if seed is None else seed
    split = json.loads((ROOT / "evals" / "split.json").read_text(encoding="utf-8"))
    used = set(split["dev"]) | set(split["test"])
    pool = [q for q in load_questions() if q["tag"] in ("bug", "other-library") and q["id"] not in used]
    return random.Random(seed).sample(pool, n), seed


def regrade(file_name):
    path = ROOT / "evals" / file_name
    data = json.loads(path.read_text(encoding="utf-8"))
    questions = {q["id"]: q for q in load_questions()}
    keep = ("search_found_gold", "cited_gold")
    rows = []
    for r in data["results"]:
        q = questions[r["id"]]
        base = {k: v for k, v in r.items() if k not in keep}
        rows.append({**base, "tag": q["tag"], "gold_pages": q["gold_pages"], **grade(q, r)})
    data["results"] = rows
    path.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    report(rows)
    print(f"-> regraded {file_name} with the current tags")


def main():
    if sys.argv[1:2] == ["regrade"]:
        regrade(sys.argv[2])
        return
    if sys.argv[1:2] == ["fresh"]:
        questions, seed = fresh_sample(seed=int(sys.argv[2]) if len(sys.argv) > 2 else None)
        print(f"fresh sample, seed {seed}: {len(questions)} questions not in dev or test\n")
        run(questions, MODEL, f"eval_fresh-{seed}")
        return
    name = sys.argv[1] if len(sys.argv) > 1 else "test"
    model = next((a for a in sys.argv[2:] if a not in ("no-check", "agent") and not a.startswith("k=")), MODEL)
    k = int(next((a[2:] for a in sys.argv[2:] if a.startswith("k=")), 3))
    check = "no-check" not in sys.argv
    agent = "agent" in sys.argv
    out = f"eval_{name}" + ("" if check else "_no-check") + ("" if k == 3 else f"_k{k}") + ("_agent" if agent else "")
    run(load_split(name), model, out, check, k, agent)


if __name__ == "__main__":
    main()
