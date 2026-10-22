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
    monkeypatch.setattr(api, "answer", lambda question: fake)
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

    def fake_events(question, cancel):
        yield "status", "search"
        yield "token", "Use a model."
        yield "done", done

    monkeypatch.setattr(api, "answer_events", fake_events)
    response = client.post("/ask/stream", json={"question": "How do I declare a body?"})
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.text.split("\n\n")[:3] == [
        'event: status\ndata: "search"',
        'event: token\ndata: "Use a model."',
        'event: done\ndata: {"trace_id": "abc123", "answer": "Use a model.", "sources": ["https://a/"], "cached": false}',
    ]


def test_ask_is_rate_limited_per_client(monkeypatch):
    from collections import defaultdict

    monkeypatch.setattr(api, "recent", defaultdict(list))
    monkeypatch.setattr(
        api, "answer", lambda question: {"trace_id": "a", "answer": "x", "sources": [], "cached": False}
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
