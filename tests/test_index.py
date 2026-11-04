import io
import socket

import pytest

from pinpoint_docs import hosted, index


def test_calls_give_up_when_the_server_never_replies(monkeypatch):
    with socket.create_server(("127.0.0.1", 0)) as silent:
        monkeypatch.setattr(index, "OLLAMA", f"http://127.0.0.1:{silent.getsockname()[1]}")
        monkeypatch.setattr(index, "TIMEOUT", 0.2)
        with pytest.raises(TimeoutError):
            index.ollama("/api/chat", {})
        with pytest.raises(TimeoutError):
            list(index.ollama_stream("/api/chat", {}))


def test_stream_stops_at_the_total_limit(monkeypatch):
    def lines(req, timeout):
        return io.BytesIO(b'{"done": false}\n' * 3)

    monkeypatch.setattr(index.urllib.request, "urlopen", lines)
    assert len(list(index.ollama_stream("/api/chat", {}))) == 3
    monkeypatch.setattr(index, "STREAM_LIMIT", -1)
    with pytest.raises(TimeoutError):
        list(index.ollama_stream("/api/chat", {}))


def test_hosted_calls_have_a_timeout(monkeypatch):
    seen = {}

    def fake(req, timeout=None):
        seen["timeout"] = timeout
        return "reply"

    monkeypatch.setenv("GEMINI_API_KEY", "test")
    monkeypatch.setattr(hosted.urllib.request, "urlopen", fake)
    assert hosted.post({}) == "reply"
    assert seen["timeout"] == index.TIMEOUT
