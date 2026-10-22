import json
import statistics

from pinpoint_docs.answer import TRACES

STEPS = ("search_seconds", "check_seconds", "agent_seconds", "answer_seconds")


def seconds(row):
    return sum(row.get(step) or 0 for step in STEPS)


def percentile(values, q):
    if not values:
        return None
    if len(values) == 1:
        return round(values[0], 2)
    return round(statistics.quantiles(values, n=100, method="inclusive")[q - 1], 2)


def load_traces():
    if not TRACES.exists():
        return []
    with TRACES.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def share(rows, test):
    return round(sum(map(test, rows)) / len(rows), 3) if rows else None


def summarize(rows):
    ok = [r for r in rows if not r.get("error")]
    total = [seconds(r) for r in ok if not r.get("cached")]
    n = len(rows)
    return {
        "requests": n,
        "latency": {"p50": percentile(total, 50), "p95": percentile(total, 95)},
        "steps_p50": {
            s.removesuffix("_seconds"): percentile([r[s] for r in ok if r.get(s) is not None], 50) for s in STEPS
        },
        "refusal_rate": share(rows, lambda r: r["answer"] == "I don't know."),
        "cache_hit_rate": share(rows, lambda r: bool(r.get("cached"))),
        "error_rate": share(rows, lambda r: bool(r.get("error"))),
        "tokens_per_1000": {
            "prompt": round(sum(r.get("prompt_tokens") or 0 for r in rows) / n * 1000) if n else None,
            "output": round(sum(r.get("output_tokens") or 0 for r in rows) / n * 1000) if n else None,
        },
    }
