import json
import os
import time
import urllib.error
import urllib.request

URL = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
RETRIES = 6
TEMPORARY = {429, 500, 502, 503, 504}


def is_hosted(model):
    return model.startswith("gemini")


def post(payload):
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY is not set")
    req = urllib.request.Request(
        URL, json.dumps(payload).encode(), {"Content-Type": "application/json", "Authorization": f"Bearer {key}"}
    )
    for attempt in range(RETRIES):
        try:
            return urllib.request.urlopen(req)
        except urllib.error.HTTPError as e:
            if e.code not in TEMPORARY or attempt == RETRIES - 1:
                raise RuntimeError(f"Gemini HTTP {e.code}: {e.read().decode(errors='replace')[:300]}") from e
            time.sleep(float(e.headers.get("Retry-After") or 5 * 2**attempt))


def as_ollama(text, usage, done=True):
    usage = usage or {}
    return {
        "message": {"role": "assistant", "content": text},
        "done": done,
        "prompt_eval_count": usage.get("prompt_tokens", 0),
        "eval_count": usage.get("completion_tokens", 0),
    }


def chat(model, messages, stream=False):
    payload = {"model": model, "messages": messages, "temperature": 0, "reasoning_effort": "none", "stream": stream}
    if not stream:
        with post(payload) as r:
            body = json.load(r)
        return as_ollama(body["choices"][0]["message"].get("content") or "", body.get("usage"))
    return chat_stream({**payload, "stream_options": {"include_usage": True}})


def chat_stream(payload):
    usage = None
    with post(payload) as r:
        for raw in r:
            line = raw.decode().strip()
            if not line.startswith("data: ") or line == "data: [DONE]":
                continue
            chunk = json.loads(line[6:])
            usage = chunk.get("usage") or usage
            for choice in chunk.get("choices", []):
                text = (choice.get("delta") or {}).get("content")
                if text:
                    yield as_ollama(text, None, done=False)
    yield as_ollama("", usage)
