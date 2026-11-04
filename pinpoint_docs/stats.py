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
    rows = []
    with TRACES.open(encoding="utf-8", errors="replace") as f:
        for line in f:
            try:
                rows.append(json.loads(line))
            except ValueError:
                continue
    return rows


def share(rows, test):
    return round(sum(map(test, rows)) / len(rows), 3) if rows else None


def summarize(rows):
    ok = [r for r in rows if not r.get("error")]
    total = [seconds(r) for r in ok if not r.get("cached")]
    return {
        "requests": len(rows),
        "latency": {"p50": percentile(total, 50), "p95": percentile(total, 95)},
        "refusal_rate": share(ok, lambda r: r["answer"] == "I don't know."),
        "cache_hit_rate": share(rows, lambda r: bool(r.get("cached"))),
        "error_rate": share(rows, lambda r: bool(r.get("error"))),
    }
