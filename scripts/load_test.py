import json
import random
import sys
import time
from concurrent.futures import ThreadPoolExecutor

from pinpoint_docs.answer import IDK, answer
from pinpoint_docs.stats import percentile
from scripts.compare_retrieval import query_text
from scripts.run_eval import ROOT, load_split

QUESTIONS = 12
CLIENTS = (1, 2, 4)


def timed(text):
    start = time.perf_counter()
    result = answer(text, use_cache=False)
    return time.perf_counter() - start, bool(result.get("error")), result["answer"] != IDK


def main():
    label = sys.argv[1] if len(sys.argv) > 1 else "run"
    picked = random.Random(0).sample(load_split("dev"), 1 + QUESTIONS * len(CLIENTS))
    texts = [query_text(q, full=True) for q in picked]
    answer(texts[0], use_cache=False)
    rows = []
    for n, clients in enumerate(CLIENTS):
        batch = texts[1 + n * QUESTIONS : 1 + (n + 1) * QUESTIONS]
        start = time.perf_counter()
        with ThreadPoolExecutor(clients) as pool:
            done = list(pool.map(timed, batch))
        wall = time.perf_counter() - start
        times = [s for s, _, _ in done]
        row = {
            "clients": clients,
            "answers_per_minute": round(len(done) / wall * 60, 1),
            "p50": percentile(times, 50),
            "p95": percentile(times, 95),
            "errors": sum(error for _, error, _ in done),
            "answered": sum(said for _, _, said in done),
        }
        rows.append(row)
        print(
            f"{clients} at once: {row['answers_per_minute']} answers/min, p50 {row['p50']:.1f}s, p95 {row['p95']:.1f}s, errors {row['errors']}/{len(done)}, answered (not I don't know) {row['answered']}/{len(done)}",
            flush=True,
        )
    out = ROOT / "evals" / f"load_{label}.json"
    out.write_text(json.dumps({"label": label, "questions": QUESTIONS, "rows": rows}, indent=1), encoding="utf-8")
    print(f"-> {out.name}")


if __name__ == "__main__":
    main()
