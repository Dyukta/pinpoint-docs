from fastapi.testclient import TestClient

from pinpoint_docs import api

client = TestClient(api.app)


def test_ask_returns_answer_and_sources(monkeypatch):
    fake = {
        "trace_id": "abc123",
        "answer": "Use a model.",
        "sources": ["https://a/"],
        "cached": False,
        "retrieved": ["x#1"],
        "error": None,
    }
    monkeypatch.setattr(api, "answer", lambda question, k, agent: fake)
    response = client.post("/ask", json={"question": "How do I declare a body?"})
    assert response.status_code == 200
    assert response.json() == {
        "trace_id": "abc123",
        "answer": "Use a model.",
        "sources": ["https://a/"],
        "cached": False,
    }


def test_ask_stream_sends_server_sent_events(monkeypatch):
    done = {"trace_id": "abc123", "answer": "Use a model.", "sources": ["https://a/"], "cached": False, "error": None}

    def fake_events(question, k, cancel, agent):
        yield "status", "search"
        yield "done", done

    monkeypatch.setattr(api, "answer_events", fake_events)
    response = client.post("/ask/stream", json={"question": "How do I declare a body?"})
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.text.split("\n\n")[:2] == [
        'event: status\ndata: "search"',
        'event: done\ndata: {"trace_id": "abc123", "answer": "Use a model.", "sources": ["https://a/"], "cached": false}',
    ]


def test_outage_is_reported_as_an_error_not_a_refusal(tmp_path, monkeypatch):
    from collections import defaultdict

    from pinpoint_docs import answer as answer_module
    from pinpoint_docs import stats

    def down(*args):
        raise ConnectionError("http://10.0.0.5:11434 refused")

    log = tmp_path / "traces.jsonl"
    monkeypatch.setattr(api, "recent", defaultdict(list))
    monkeypatch.setattr(answer_module, "respond", down)
    monkeypatch.setattr(answer_module, "TRACES", log)
    monkeypatch.setattr(stats, "TRACES", log)
    body = {"question": "How do I declare a body?"}

    response = client.post("/ask", json=body)
    assert response.status_code == 503 and response.headers["retry-after"] == "30"
    assert response.json()["detail"] == api.UNAVAILABLE

    stream = client.post("/ask/stream", json=body)
    assert stream.text == f'event: error\ndata: "{api.UNAVAILABLE}"\n\n'

    assert "10.0.0.5" not in response.text + stream.text
    assert "10.0.0.5" in log.read_text(encoding="utf-8")
    numbers = client.get("/stats").json()
    assert numbers["error_rate"] == 1.0 and numbers["refusal_rate"] is None


def test_answer_still_arrives_when_the_trace_cannot_be_saved(tmp_path, monkeypatch, caplog):
    from collections import defaultdict

    from pinpoint_docs import answer as answer_module

    def fake_respond(*args):
        yield "result", {"answer": "Use a model.", "sources": ["https://a/"], "cached": False}

    monkeypatch.setattr(api, "recent", defaultdict(list))
    monkeypatch.setattr(answer_module, "respond", fake_respond)
    monkeypatch.setattr(answer_module, "TRACES", tmp_path / "missing" / "traces.jsonl")
    body = {"question": "How do I declare a body?"}

    response = client.post("/ask", json=body)
    assert response.status_code == 200 and response.json()["answer"] == "Use a model."

    stream = client.post("/ask/stream", json=body)
    assert stream.text.startswith("event: done") and "Use a model." in stream.text
    assert "Could not save trace" in caplog.text


def test_stream_ends_with_an_error_when_the_worker_crashes(monkeypatch):
    from collections import defaultdict

    def crash(*args, **kwargs):
        raise RuntimeError("secret detail")

    monkeypatch.setattr(api, "recent", defaultdict(list))
    monkeypatch.setattr(api, "answer_events", crash)
    stream = client.post("/ask/stream", json={"question": "How do I declare a body?"})
    assert stream.text == f'event: error\ndata: "{api.UNAVAILABLE}"\n\n'


def test_corrupt_trace_lines_are_skipped(tmp_path, monkeypatch):
    import json

    from pinpoint_docs import stats

    good = {"trace_id": "a1", "time": "t", "question": "q", "answer": "x", "error": None}
    line = (json.dumps(good) + "\n").encode()
    cut_mid_character = '{"trace_id": "b2", "question": "café'.encode()[:-1]
    log = tmp_path / "traces.jsonl"
    log.write_bytes(line + b'{"trace_id": "half\n' + b"\n" + line + cut_mid_character)
    monkeypatch.setattr(stats, "TRACES", log)

    numbers = client.get("/stats")
    assert numbers.status_code == 200 and numbers.json()["requests"] == 2
    traces = client.get("/traces")
    assert traces.status_code == 200 and traces.json()["total"] == 2
    assert client.get("/traces/a1").status_code == 200


def test_refusal_rate_leaves_out_failed_requests():
    from pinpoint_docs.stats import summarize

    idk = {"answer": "I don't know.", "error": None}
    failed = {"answer": "I don't know.", "error": "ConnectionError: down"}
    answered = {"answer": "Use a model.", "error": None}
    assert summarize([idk, failed, answered])["refusal_rate"] == 0.5


def test_ask_is_rate_limited_per_client(monkeypatch):
    from collections import defaultdict

    monkeypatch.setattr(api, "recent", defaultdict(list))
    monkeypatch.setattr(
        api, "answer", lambda question, k, agent: {"trace_id": "a", "answer": "x", "sources": [], "cached": False}
    )
    codes = [
        client.post("/ask", json={"question": "How do I declare a body?"}).status_code for _ in range(api.LIMIT + 1)
    ]
    assert codes == [200] * api.LIMIT + [429]


def test_ask_rejects_empty_question():
    assert client.post("/ask", json={"question": ""}).status_code == 422
    assert client.post("/ask", json={}).status_code == 422


def test_stats_and_traces_read_the_trace_log(tmp_path, monkeypatch):
    import json

    from pinpoint_docs import stats

    log = tmp_path / "traces.jsonl"
    rows = [
        {
            "trace_id": "a1",
            "time": "t1",
            "question": "q1",
            "answer": "Use a model.",
            "cached": False,
            "error": None,
            "search_seconds": 1.0,
            "check_seconds": 10.0,
            "answer_seconds": 9.0,
            "prompt_tokens": 3000,
            "output_tokens": 100,
        },
        {
            "trace_id": "b2",
            "time": "t2",
            "question": "q2",
            "answer": "I don't know.",
            "cached": False,
            "error": None,
            "search_seconds": 1.0,
            "check_seconds": 9.0,
            "answer_seconds": None,
            "prompt_tokens": 2000,
            "output_tokens": 1,
        },
        {
            "trace_id": "c3",
            "time": "t3",
            "question": "q1",
            "answer": "Use a model.",
            "cached": True,
            "error": None,
            "search_seconds": 0.5,
            "check_seconds": None,
            "answer_seconds": None,
            "prompt_tokens": 0,
            "output_tokens": 0,
        },
    ]
    log.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    monkeypatch.setattr(stats, "TRACES", log)

    body = client.get("/stats").json()
    assert body["requests"] == 3
    assert body["latency"]["p50"] == 15.0
    assert body["refusal_rate"] == 0.333 and body["cache_hit_rate"] == 0.333 and body["error_rate"] == 0.0

    recent = client.get("/traces").json()
    assert recent["total"] == 3
    assert [t["trace_id"] for t in recent["items"]] == ["c3", "b2", "a1"]
    page = client.get("/traces?limit=2&offset=2").json()
    assert page["total"] == 3 and [t["trace_id"] for t in page["items"]] == ["a1"]
    assert client.get("/traces/b2").json()["answer"] == "I don't know."
    assert client.get("/traces/zz").status_code == 404


def test_eval_summary(tmp_path, monkeypatch):
    import json

    run = tmp_path / "eval_test.json"
    rows = [
        {
            "tag": "docs",
            "pass": True,
            "failure": None,
            "answer": "x",
            "search_seconds": 1,
            "check_seconds": 10,
            "answer_seconds": 9,
        },
        {
            "tag": "docs",
            "pass": False,
            "failure": "search_missed_gold",
            "answer": "I don't know.",
            "search_seconds": 1,
            "check_seconds": 10,
            "answer_seconds": None,
        },
        {
            "tag": "bug",
            "pass": True,
            "failure": None,
            "answer": "I don't know.",
            "search_seconds": 1,
            "check_seconds": 10,
            "answer_seconds": None,
        },
    ]
    run.write_text(json.dumps({"results": rows}), encoding="utf-8")
    monkeypatch.setattr(api, "EVAL_RUN", run)
    monkeypatch.setattr(api, "NO_CHECK_RUN", tmp_path / "missing.json")
    body = client.get("/eval").json()
    assert body["passed"] == 2 and body["questions"] == 3
    assert body["failures"] == {"search_missed_gold": 1}
    assert body["by_tag"] == {"bug": {"passed": 1, "total": 1}, "docs": {"passed": 1, "total": 2}}
    assert body["without_check"] is None


def test_ask_answers_one_at_a_time_and_returns_503_when_the_queue_is_full(monkeypatch):
    import threading
    import time
    from collections import defaultdict
    from concurrent.futures import ThreadPoolExecutor

    release, lock = threading.Event(), threading.Lock()
    now = {"count": 0, "most": 0}

    def slow(question, k, agent):
        with lock:
            now["count"] += 1
            now["most"] = max(now["most"], now["count"])
        release.wait(5)
        with lock:
            now["count"] -= 1
        return {"trace_id": "a", "answer": "x", "sources": [], "cached": False}

    monkeypatch.setattr(api, "recent", defaultdict(list))
    monkeypatch.setattr(api, "answer", slow)
    full = api.RUNNING + api.WAITING
    body = {"question": "How do I declare a body?"}
    with ThreadPoolExecutor(full) as pool:
        pending = [pool.submit(client.post, "/ask", json=body) for _ in range(full)]
        deadline = time.monotonic() + 5
        while api.slots._value and time.monotonic() < deadline:
            time.sleep(0.01)
        busy = client.post("/ask", json=body)
        release.set()
        codes = [p.result().status_code for p in pending]
    assert busy.status_code == 503 and busy.headers["retry-after"] == "30"
    assert codes == [200] * full
    assert now["most"] == api.RUNNING
    assert api.slots._value == full
