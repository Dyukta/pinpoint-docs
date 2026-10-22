import json
import statistics
import sys
import time

from pinpoint_docs.answer import IDK, MODEL, chat
from scripts.compare_retrieval import query_text
from scripts.run_eval import ROOT, load_split

SYSTEM = f"Answer the FastAPI question. Keep it to 2 to 5 sentences. If you are not sure of the answer, reply with exactly: {IDK}"


def main():
    name = sys.argv[1] if len(sys.argv) > 1 else "test"
    model = sys.argv[2] if len(sys.argv) > 2 else MODEL
    questions = load_split(name)
    results = []
    for n, q in enumerate(questions, 1):
        start = time.perf_counter()
        reply = chat(model, SYSTEM, query_text(q, full=True))
        text = reply["message"]["content"].strip()
        said_idk = "don't know" in text.lower()
        results.append(
            {
                "id": q["id"],
                "title": q["title"],
                "tag": q["tag"],
                "gold_pages": q["gold_pages"],
                "answer": text,
                "said_idk": said_idk,
                "seconds": round(time.perf_counter() - start, 2),
                "prompt_tokens": reply.get("prompt_eval_count", 0),
                "output_tokens": reply.get("eval_count", 0),
            }
        )
        print(
            f"{n}/{len(questions)} {q['tag']:<13} {'IDK' if said_idk else 'answered'} {results[-1]['seconds']:5.1f}s  #{q['id']} {q['title'][:60]}",
            flush=True,
        )

    out = ROOT / "evals" / f"baseline_{name}_{model.replace(':', '-')}.json"
    out.write_text(json.dumps({"model": model, "results": results}, indent=1, ensure_ascii=False), encoding="utf-8")
    docs = [r for r in results if r["gold_pages"]]
    other = [r for r in results if not r["gold_pages"]]
    print(f"\ndocs questions: said I don't know {sum(r['said_idk'] for r in docs)}/{len(docs)}")
    print(f"non-docs questions: said I don't know {sum(r['said_idk'] for r in other)}/{len(other)}")
    print(
        f"median seconds {statistics.median(r['seconds'] for r in results):.1f}, median tokens: prompt {statistics.median(r['prompt_tokens'] for r in results):.0f}, output {statistics.median(r['output_tokens'] for r in results):.0f}"
    )
    print(f"-> {out.name}")


if __name__ == "__main__":
    main()
