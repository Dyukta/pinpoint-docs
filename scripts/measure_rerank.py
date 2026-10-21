import json
import statistics
import sys
import time
from math import comb

import numpy as np

from pinpoint_docs.index import document
from pinpoint_docs.rerank import rerank
from pinpoint_docs.search import BM25, rrf
from scripts.compare_retrieval import embed_all, headings, normalize, query_text
from scripts.measure_gate import without_code
from scripts.run_eval import ROOT, load_split

POOL = 20
QUERIES = {"full question": lambda q: query_text(q, full=True), "no code": without_code}


def sign_test(wins, losses):
    n = wins + losses
    return 1.0 if n == 0 else min(1.0, 2 * sum(comb(n, i) for i in range(min(wins, losses) + 1)) / 2**n)


def first_gold(ranking, chunks, gold):
    return next((r for r, i in enumerate(ranking) if chunks[i]["page"] in gold), None)


def main():
    name = sys.argv[1] if len(sys.argv) > 1 else "dev"
    questions = [q for q in load_split(name) if q["gold_pages"]]
    chunks = headings(1500)
    vectors = normalize(embed_all([document(c) for c in chunks])[0])
    query_vectors = normalize(embed_all([f"search_query: {query_text(q, True)}" for q in questions])[0])
    bm25 = BM25([f"{c['title']}\n{c['text']}" for c in chunks])

    rows, timings = [], {v: [] for v in QUERIES}
    for q, qv in zip(questions, query_vectors):
        text = query_text(q, full=True)
        fused = [i for i, _ in rrf([bm25.rank(text, 50), [int(i) for i in np.argsort(-(vectors @ qv))[:50]]])]
        row = {"id": q["id"], "hybrid": first_gold(fused, chunks, q["gold_pages"])}
        pool = fused[:POOL]
        for variant, make in QUERIES.items():
            start = time.perf_counter()
            order = rerank(make(q), [f"{chunks[i]['title']}\n{chunks[i]['text']}" for i in pool])
            timings[variant].append(time.perf_counter() - start)
            reranked = [pool[i] for i in order] + fused[POOL:]
            row[variant] = first_gold(reranked, chunks, q["gold_pages"])
        rows.append(row)

    out = ROOT / "evals" / f"rerank_{name}.json"
    out.write_text(json.dumps({"split": name, "pool": POOL, "rows": rows}, indent=1), encoding="utf-8")
    hit = lambda rank, k: rank is not None and rank < k
    print(f"{len(rows)} {name} docs questions, rerank top {POOL} -> {out.name}\n")
    print(f"{'search':<26} hit@1   hit@5   vs hybrid at hit@5          rerank p50")
    print(f"{'hybrid':<26} {sum(hit(r['hybrid'], 1) for r in rows):>3}     {sum(hit(r['hybrid'], 5) for r in rows):>3}")
    for variant in QUERIES:
        wins = sum(hit(r[variant], 5) and not hit(r["hybrid"], 5) for r in rows)
        losses = sum(hit(r["hybrid"], 5) and not hit(r[variant], 5) for r in rows)
        label = f"hybrid + rerank, {variant}"
        print(f"{label:<26} {sum(hit(r[variant], 1) for r in rows):>3}     {sum(hit(r[variant], 5) for r in rows):>3}     +{wins} / -{losses}, p = {sign_test(wins, losses):.2f}      {statistics.median(timings[variant]):.2f} s")


if __name__ == "__main__":
    main()
