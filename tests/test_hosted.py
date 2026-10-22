import io
import json

from pinpoint_docs import hosted


def sse(*chunks):
    return io.BytesIO("".join(f"data: {json.dumps(c)}\n\n" for c in chunks).encode() + b"data: [DONE]\n\n")


def test_stream_is_turned_into_ollama_chunks(monkeypatch):
    body = sse(
        {"choices": [{"delta": {"content": "EXCERPTS: 1\nANSWER: Use"}}]},
        {"choices": [{"delta": {"content": " a model."}}]},
        {"choices": [], "usage": {"prompt_tokens": 1200, "completion_tokens": 9}},
    )
    monkeypatch.setattr(hosted, "post", lambda payload: body)
    parts = list(hosted.chat("gemini-2.5-flash", [], stream=True))
    assert "".join(p["message"]["content"] for p in parts) == "EXCERPTS: 1\nANSWER: Use a model."
    assert [p["done"] for p in parts] == [False, False, True]
    assert (parts[-1]["prompt_eval_count"], parts[-1]["eval_count"]) == (1200, 9)


def test_plain_reply_and_model_choice(monkeypatch):
    reply = {"choices": [{"message": {"content": "YES"}}], "usage": {"prompt_tokens": 50, "completion_tokens": 1}}
    monkeypatch.setattr(hosted, "post", lambda payload: io.BytesIO(json.dumps(reply).encode()))
    assert hosted.chat("gemini-2.5-flash", [])["message"]["content"] == "YES"
    empty = {"choices": [{"message": {"role": "assistant"}, "finish_reason": "length"}]}
    monkeypatch.setattr(hosted, "post", lambda payload: io.BytesIO(json.dumps(empty).encode()))
    assert hosted.chat("gemini-2.5-flash", [])["message"]["content"] == ""
    assert hosted.is_hosted("gemini-2.5-flash") and not hosted.is_hosted("llama3.2")
