import json
from collections import Counter

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from pinpoint_docs.answer import answer
from pinpoint_docs.index import ROOT
from pinpoint_docs.stats import load_traces, seconds, summarize

EVAL_RUN = ROOT / "evals" / "eval_test_llama3.2.json"

app = FastAPI(title="Pinpoint", summary="Answers FastAPI questions from the FastAPI docs, with links, or says I don't know.")


class Question(BaseModel):
    question: str = Field(min_length=3, max_length=20000)


class Answer(BaseModel):
    trace_id: str
    answer: str
    sources: list[str]
    cached: bool


@app.post("/ask")
def ask(body: Question) -> Answer:
    return Answer(**answer(body.question))


@app.get("/stats")
def stats(last: int = Query(200, ge=1, le=100000)):
    return summarize(load_traces()[-last:])


@app.get("/traces")
def traces(limit: int = Query(50, ge=1, le=500)):
    return [
        {
            "trace_id": t["trace_id"],
            "time": t["time"],
            "question": t["question"][:200],
            "answer": t["answer"][:200],
            "cached": bool(t.get("cached")),
            "error": t.get("error"),
            "seconds": round(seconds(t), 2),
        }
        for t in reversed(load_traces()[-limit:])
    ]


@app.get("/traces/{trace_id}")
def trace(trace_id: str):
    for t in reversed(load_traces()):
        if t["trace_id"] == trace_id:
            return t
    raise HTTPException(status_code=404, detail="Trace not found")


@app.get("/eval")
def eval_results():
    if not EVAL_RUN.exists():
        raise HTTPException(status_code=404, detail="No test run yet")
    rows = json.loads(EVAL_RUN.read_text(encoding="utf-8"))["results"]
    tags = sorted({r["tag"] for r in rows})
    return {
        "run": EVAL_RUN.name,
        "questions": len(rows),
        "passed": sum(r["pass"] for r in rows),
        "failures": dict(Counter(r["failure"] for r in rows if r["failure"]).most_common()),
        "by_tag": {tag: {"passed": sum(r["pass"] for r in rows if r["tag"] == tag), "total": sum(r["tag"] == tag for r in rows)} for tag in tags},
        **summarize(rows),
    }
