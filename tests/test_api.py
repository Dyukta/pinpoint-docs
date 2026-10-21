from fastapi.testclient import TestClient

from pinpoint_docs import api

client = TestClient(api.app)


def test_ask_returns_answer_and_sources(monkeypatch):
    fake = {"trace_id": "abc123", "answer": "Use a model.", "sources": ["https://a/"], "cached": False, "retrieved": ["x#1"], "error": None}
    monkeypatch.setattr(api, "answer", lambda question: fake)
    response = client.post("/ask", json={"question": "How do I declare a body?"})
    assert response.status_code == 200
    assert response.json() == {"trace_id": "abc123", "answer": "Use a model.", "sources": ["https://a/"], "cached": False}


def test_ask_rejects_empty_question():
    assert client.post("/ask", json={"question": ""}).status_code == 422
    assert client.post("/ask", json={}).status_code == 422
