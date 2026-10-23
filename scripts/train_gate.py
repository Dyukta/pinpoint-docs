import json
import random
import statistics
import sys

import numpy as np

from pinpoint_docs.stats import seconds
from scripts.compare_retrieval import embed_all, normalize, query_text
from scripts.run_eval import ROOT, load_questions

FOLDS = 5
L2 = 1.0
STEPS = 25
BAR_PASSED = 43
BAR_IDK = 34


def vectors(questions):
    matrix, _ = embed_all([f"search_query: {query_text(q, full=True)}" for q in questions])
    return normalize(matrix)


def features(x, mean, std):
    return np.hstack([(x - mean) / std, np.ones((len(x), 1))])


def train(x, y):
    mean, std = x.mean(0), x.std(0) + 1e-8
    xb = features(x, mean, std)
    weight = np.where(y == 1, len(y) / (2 * y.sum()), len(y) / (2 * (len(y) - y.sum())))
    penalty = np.r_[np.full(x.shape[1], L2), 0.0]
    w = np.zeros(xb.shape[1])
    for _ in range(STEPS):
        p = 1 / (1 + np.exp(-xb @ w))
        grad = xb.T @ (weight * (p - y)) + penalty * w
        hess = xb.T @ (xb * (weight * p * (1 - p))[:, None]) + np.diag(penalty)
        w -= np.linalg.solve(hess, grad)
    return w, mean, std


def probability(model, x):
    w, mean, std = model
    return 1 / (1 + np.exp(-features(x, mean, std) @ w))


def folds(ids, labels, seed=0):
    rng = random.Random(seed)
    out = [[] for _ in range(FOLDS)]
    for label in (1, 0):
        group = [i for i, y in zip(ids, labels) if y == label]
        rng.shuffle(group)
        for n, i in enumerate(group):
            out[n % FOLDS].append(i)
    return out


def main():
    name = sys.argv[1] if len(sys.argv) > 1 else "eval_dev_no-check_llama3.2.json"
    split = json.loads((ROOT / "evals" / "split.json").read_text(encoding="utf-8"))
    questions = load_questions()
    by_id = {q["id"]: q for q in questions}
    used = set(split["dev"]) | set(split["test"])
    extra = [q for q in questions if q["tag"] in ("bug", "other-library") and q["id"] not in used]
    dev = [by_id[i] for i in split["dev"]]
    x_extra, x_dev = vectors(extra), vectors(dev)
    y_extra = np.zeros(len(extra))
    y_dev = np.array([1.0 if q["gold_pages"] else 0.0 for q in dev])
    row_of = {q["id"]: n for n, q in enumerate(dev)}

    chance = {}
    for part in folds([q["id"] for q in dev], y_dev):
        held = [row_of[i] for i in part]
        kept = [n for n in range(len(dev)) if n not in held]
        model = train(np.vstack([x_dev[kept], x_extra]), np.r_[y_dev[kept], y_extra])
        for n, p in zip(held, probability(model, x_dev[held])):
            chance[dev[n]["id"]] = float(p)

    runs = {r["id"]: r for r in json.loads((ROOT / "evals" / name).read_text(encoding="utf-8"))["results"]}
    rows = []
    for q in dev:
        r = runs[q["id"]]
        yes = chance[q["id"]] > 0.5
        idk = r["said_idk"] or not yes
        passed = r["pass"] if yes else not q["gold_pages"]
        took = seconds(r) if yes else r["search_seconds"]
        rows.append({"id": q["id"], "docs": bool(q["gold_pages"]), "chance": round(chance[q["id"]], 3), "yes": yes, "said_idk": idk, "pass": passed, "seconds": took})

    docs = [r for r in rows if r["docs"]]
    other = [r for r in rows if not r["docs"]]
    passed = sum(r["pass"] for r in rows)
    idk = sum(r["said_idk"] for r in other)
    out = ROOT / "evals" / "gate_trained_dev.json"
    out.write_text(json.dumps({"no_check_file": name, "folds": FOLDS, "l2": L2, "rows": rows}, indent=1), encoding="utf-8")
    print(f"training: {len(extra)} extra out-of-scope questions always in, dev in {FOLDS} folds, test untouched")
    print(f"gate YES on docs {sum(r['yes'] for r in docs)}/{len(docs)}, gate NO on out of scope {sum(not r['yes'] for r in other)}/{len(other)}")
    print(f"docs cited gold {sum(r['pass'] for r in docs)}/{len(docs)}, out of scope said I don't know {idk}/{len(other)}")
    print(f"passed {passed}/{len(rows)}, p50 {statistics.median(r['seconds'] for r in rows):.1f}s")
    print(f"bar: passed > {BAR_PASSED}/80 and I don't know >= {BAR_IDK}/40 -> {'PASS' if passed > BAR_PASSED and idk >= BAR_IDK else 'FAIL'}")
    print(f"-> {out.name}")


if __name__ == "__main__":
    main()
