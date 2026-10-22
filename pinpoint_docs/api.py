import asyncio
import json
import threading
import time
from collections import Counter, defaultdict

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from pinpoint_docs.answer import answer, answer_events
from pinpoint_docs.index import ROOT
from pinpoint_docs.stats import load_traces, seconds, summarize

EVAL_RUN = ROOT / "evals" / "eval_test_llama3.2.json"
NO_CHECK_RUN = ROOT / "evals" / "eval_test_no-check_llama3.2.json"
DASHBOARD = ROOT / "dashboard" / "dist"
LIMIT = 10
WINDOW_SECONDS = 60
recent = defaultdict(list)
recent_lock = threading.Lock()

app = FastAPI(
    title="Pinpoint", summary="Answers FastAPI questions from the FastAPI docs, with links, or says I don't know."
)


class Question(BaseModel):
    question: str = Field(min_length=3, max_length=20000)


class Answer(BaseModel):
    trace_id: str
    answer: str
    sources: list[str]
    cached: bool


def rate_limit(request: Request):
    now = time.monotonic()
    ip = request.client.host if request.client else "unknown"
    with recent_lock:
        times = [t for t in recent[ip] if now - t < WINDOW_SECONDS]
        if len(times) >= LIMIT:
            recent[ip] = times
            raise HTTPException(
                status_code=429,
                detail=f"At most {LIMIT} questions per minute",
                headers={"Retry-After": str(WINDOW_SECONDS)},
            )
        recent[ip] = [*times, now]


@app.post("/ask", dependencies=[Depends(rate_limit)])
def ask(body: Question) -> Answer:
    return Answer(**answer(body.question))


@app.post("/ask/stream", dependencies=[Depends(rate_limit)])
def ask_stream(body: Question):
    cancel = threading.Event()

    async def sse():
        loop = asyncio.get_running_loop()
        events = asyncio.Queue()

        def produce():
            for event in answer_events(body.question, cancel=cancel):
                loop.call_soon_threadsafe(events.put_nowait, event)

        threading.Thread(target=produce, daemon=True).start()
        try:
            kind = None
            while kind != "done":
                kind, value = await events.get()
                data = Answer(**value).model_dump() if kind == "done" else value
                yield f"event: {kind}\ndata: {json.dumps(data)}\n\n"
        finally:
            cancel.set()

    return StreamingResponse(sse(), media_type="text/event-stream")


@app.get("/stats")
def stats(last: int = Query(200, ge=1, le=100000)):
    return summarize(load_traces()[-last:])


@app.get("/traces")
def traces(limit: int = Query(20, ge=1, le=500), offset: int = Query(0, ge=0)):
    newest_first = load_traces()[::-1]
    return {
        "total": len(newest_first),
        "items": [
            {
                "trace_id": t["trace_id"],
                "time": t["time"],
                "question": t["question"][:200],
                "answer": t["answer"][:200],
                "cached": bool(t.get("cached")),
                "error": t.get("error"),
                "seconds": round(seconds(t), 2),
            }
            for t in newest_first[offset : offset + limit]
        ],
    }


@app.get("/traces/{trace_id}")
def trace(trace_id: str):
    for t in reversed(load_traces()):
        if t["trace_id"] == trace_id:
            return t
    raise HTTPException(status_code=404, detail="Trace not found")


def summarize_run(path):
    rows = json.loads(path.read_text(encoding="utf-8"))["results"]
    tags = sorted({r["tag"] for r in rows})
    return {
        "run": path.name,
        "questions": len(rows),
        "passed": sum(r["pass"] for r in rows),
        "failures": dict(Counter(r["failure"] for r in rows if r["failure"]).most_common()),
        "by_tag": {
            tag: {
                "passed": sum(r["pass"] for r in rows if r["tag"] == tag),
                "total": sum(r["tag"] == tag for r in rows),
            }
            for tag in tags
        },
        **summarize(rows),
    }


@app.get("/eval")
def eval_results():
    if not EVAL_RUN.exists():
        raise HTTPException(status_code=404, detail="No test run yet")
    return {**summarize_run(EVAL_RUN), "without_check": summarize_run(NO_CHECK_RUN) if NO_CHECK_RUN.exists() else None}


if DASHBOARD.exists():
    app.mount("/", StaticFiles(directory=DASHBOARD, html=True), name="dashboard")
