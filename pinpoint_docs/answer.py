import hashlib
import json
import re
import sys
import time
import uuid
from datetime import UTC, datetime
from functools import cache

import chromadb

from pinpoint_docs import hosted
from pinpoint_docs.index import CACHE, COLLECTION, DB, ROOT, ollama, ollama_stream
from pinpoint_docs.search import embed_question, search

TRACES = ROOT / "data" / "traces.jsonl"
MODEL = "llama3.2"
IDK = "I don't know."
CACHE_DISTANCE = 0.03
EMPTY = {
    "answer": IDK,
    "sources": [],
    "retrieved": [],
    "scores": [],
    "answerable": False,
    "cached": False,
    "search_seconds": None,
    "check_seconds": None,
    "answer_seconds": None,
    "prompt_tokens": 0,
    "output_tokens": 0,
    "calls": [],
    "agent": None,
    "agent_seconds": None,
}
SYSTEM = f"""You answer FastAPI questions using only the numbered documentation excerpts you are given.
Use only facts and code that appear in the excerpts. Never invent code, parameters or behavior.
Do not repeat the code from the question. Keep the answer to 2 to 5 sentences, plus a short code example copied from an excerpt if it helps.

Reply in exactly this format:
EXCERPTS: the numbers of the excerpts your answer is based on, like 2, 4
ANSWER: your answer

If no excerpt answers the question, reply with:
EXCERPTS: none
ANSWER: {IDK}"""
CHECK = "You check whether documentation excerpts answer a question. Reply with only YES or NO."
CHECK_ASK = "Do these excerpts contain the answer to the question? Reply YES or NO."
ANSWER_ASK = f"Now answer the question from the excerpts.\n\n{SYSTEM}"
AGENT = (
    "The documentation excerpts found for this FastAPI question did not answer it. "
    "If the FastAPI docs might still cover it, call search_docs once with a better query in the docs' own words. "
    "If the question is not about a documented FastAPI feature, do not call the tool."
)
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_docs",
            "description": "Search the FastAPI documentation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "A short query of at most 12 words, using feature, class and function names",
                    }
                },
                "required": ["query"],
            },
        },
    }
]
OPTIONS = {"temperature": 0, "num_ctx": 8192, "num_gpu": 99}
REPLY = re.compile(r"EXCERPTS:(.*?)\n\s*ANSWER:(.*)", re.S | re.I)
ANSWER_START = re.compile(r"ANSWER:\s*", re.I)
EXCERPT_REF = re.compile(
    r",?\s*\(?\b(?:as (?:shown|seen|described) )?(?:in |from |see )?excerpts? \d+(?:\s*(?:,|and)\s*\d+)*\)?", re.I
)
LINK = re.compile(r"https?://[^\s)\]>\"'`]*[^\s)\]>\"'`.,;:!?]")
SECRETS = [
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"), "[email]"),
    (re.compile(r"(?i)\b(password|passwd|secret|token|api[_-]?key)(\s*[=:]\s*)\S+"), r"\1\2[redacted]"),
    (re.compile(r"\b(?=[\w-]*\d)(?=[\w-]*[A-Za-z])[\w-]{24,}\b"), "[redacted]"),
]


class Cancelled(Exception):
    pass


def redact(text):
    for pattern, replacement in SECRETS:
        text = pattern.sub(replacement, text)
    return text


def strip_links(text, hits):
    allowed = {c["url"] for c in hits} | {url for c in hits for url in LINK.findall(c.get("text", ""))}
    return LINK.sub(lambda m: m[0] if m[0] in allowed else "[link removed]", text)


def sources(numbers, hits):
    return list(dict.fromkeys(hits[n - 1]["url"] for n in numbers if 1 <= n <= len(hits)))


def parse(reply, hits):
    match = REPLY.search(reply)
    if not match:
        return IDK, []
    urls = sources([int(n) for n in re.findall(r"\d+", match.group(1))], hits)
    text = EXCERPT_REF.sub("", strip_links(match.group(2).strip(), hits))
    if not urls or "don't know" in text.lower():
        return IDK, []
    return text, urls


def excerpts(hits):
    return "\n\n".join(f"Excerpt {i} ({c['title']} > {c['section']}):\n{c['text']}" for i, c in enumerate(hits, 1))


def chat(model, system, user, history=(), stream=False, tools=None, **options):
    messages = [{"role": "system", "content": system}, *history, {"role": "user", "content": user}]
    if hosted.is_hosted(model):
        return hosted.chat(model, messages, stream)
    payload = {"model": model, "messages": messages, "stream": stream, "options": {**OPTIONS, **options}}
    if tools:
        payload["tools"] = tools
    return ollama_stream("/api/chat", payload) if stream else ollama("/api/chat", payload)


def search_again(question, model):
    reply = chat(model, AGENT, question, tools=TOOLS)
    for call in reply["message"].get("tool_calls") or []:
        if call["function"]["name"] == "search_docs":
            return str(call["function"]["arguments"].get("query", "")).strip(), reply
    return None, reply


def to_seconds(nanoseconds):
    return round(nanoseconds / 1e9, 2)


def timing(step, reply):
    return {
        "step": step,
        "prompt_tokens": reply.get("prompt_eval_count", 0),
        "output_tokens": reply.get("eval_count", 0),
        "load_seconds": to_seconds(reply.get("load_duration", 0)),
        "read_seconds": to_seconds(reply.get("prompt_eval_duration", 0)),
        "write_seconds": to_seconds(reply.get("eval_duration", 0)),
    }


def prompt(question, context):
    return f"Question:\n{question}\n\nExcerpts:\n\n{context}"


def is_answerable(question, context, model=MODEL):
    reply = chat(model, CHECK, f"{prompt(question, context)}\n\n{CHECK_ASK}", num_predict=3)
    return reply["message"]["content"].strip().upper().startswith("YES"), reply


def stream_answer(question, context, model, verdict=None):
    if verdict:
        history = [
            {"role": "user", "content": f"{prompt(question, context)}\n\n{CHECK_ASK}"},
            {"role": "assistant", "content": verdict["message"]["content"]},
        ]
        parts = chat(model, CHECK, ANSWER_ASK, history=history, stream=True)
    else:
        parts = chat(model, SYSTEM, prompt(question, context), stream=True)
    text, sent = "", 0
    for part in parts:
        text += part["message"]["content"]
        start = ANSWER_START.search(text)
        if start and len(text) - start.end() > sent:
            yield "token", text[start.end() + sent :]
            sent = len(text) - start.end()
        if part["done"]:
            return {**part, "message": {"role": "assistant", "content": text}}
    raise ConnectionError("Ollama stream ended before the answer was done")


@cache
def answer_cache():
    return chromadb.PersistentClient(str(DB)).get_or_create_collection(
        CACHE, configuration={"hnsw": {"space": "cosine"}}
    )


def settings_key(model, k, check=True, agent=False):
    settings = [model, k, check, SYSTEM, CHECK, CHECK_ASK, ANSWER_ASK, OPTIONS, COLLECTION, EXCERPT_REF.pattern]
    if agent:
        settings += [AGENT, TOOLS]
    return hashlib.sha256(json.dumps(settings, sort_keys=True).encode()).hexdigest()[:16]


def cached_answer(vector, key):
    hit = answer_cache().query(query_embeddings=[vector], n_results=1, where={"settings": key})
    if hit["ids"][0] and hit["distances"][0][0] <= CACHE_DISTANCE:
        meta = hit["metadatas"][0][0]
        return {
            "answer": meta["answer"],
            "sources": json.loads(meta["sources"]),
            "retrieved": json.loads(meta["retrieved"]),
        }
    return None


def remember(vector, key, question, result):
    answer_cache().add(
        ids=[uuid.uuid4().hex],
        embeddings=[vector],
        documents=[redact(question)],
        metadatas=[
            {
                "settings": key,
                "answer": result["answer"],
                "sources": json.dumps(result["sources"]),
                "retrieved": json.dumps(result["retrieved"]),
            }
        ],
    )


def answer_events(question, k=3, model=MODEL, use_cache=True, check=True, cancel=None, agent=False):
    trace = {
        "trace_id": uuid.uuid4().hex[:12],
        "time": datetime.now(UTC).isoformat(timespec="seconds"),
        "model": model,
        "question": redact(question),
    }
    try:
        events = respond(question, k, model, use_cache, check, agent)
        for kind, value in events:
            if cancel and cancel.is_set():
                events.close()
                raise Cancelled
            if kind == "result":
                trace |= value
            else:
                yield kind, value
        trace["error"] = None
    except Cancelled:
        trace |= {**EMPTY, "error": "cancelled"}
    except Exception as e:
        trace |= {**EMPTY, "error": f"{type(e).__name__}: {e}"}
    with TRACES.open("a", encoding="utf-8") as f:
        f.write(json.dumps(trace, ensure_ascii=False) + "\n")
    yield "done", trace


def answer(question, k=3, model=MODEL, use_cache=True, check=True, agent=False):
    *_, (_, trace) = answer_events(question, k, model, use_cache, check, agent=agent)
    return trace


def respond(question, k, model, use_cache, check=True, agent=False):
    start = time.perf_counter()
    yield "status", "search"
    vector = embed_question(question)
    key = settings_key(model, k, check, agent)
    hit = cached_answer(vector, key) if use_cache else None
    if hit:
        yield "result", {**EMPTY, **hit, "cached": True, "search_seconds": round(time.perf_counter() - start, 2)}
        return
    hits = search(question, k, vector=vector)
    searched = time.perf_counter()
    context = excerpts(hits)
    if check:
        yield "status", "check"
    ok, verdict = is_answerable(question, context, model) if check else (True, {})
    checked = time.perf_counter()
    calls = [timing("check", verdict)] if check else []
    first_hits, retry = hits, None
    if check and agent and not ok:
        yield "status", "search again"
        query, call = search_again(question, model)
        calls.append(timing("agent", call))
        retry = {"query": query, "retrieved": [], "answerable": False}
        new_hits = search(query, k) if query else []
        if {c["page"] for c in new_hits} - {c["page"] for c in hits}:
            yield "status", "check"
            again, second = is_answerable(question, excerpts(new_hits), model)
            calls.append(timing("check", second))
            retry |= {"retrieved": [c["id"] for c in new_hits], "answerable": again}
            if again:
                ok, verdict, hits, context = True, second, new_hits, excerpts(new_hits)
    retried = time.perf_counter()
    text, urls = IDK, []
    if ok:
        yield "status", "answer"
        reply = yield from stream_answer(question, context, model, verdict)
        calls.append(timing("answer", reply))
        text, urls = parse(reply["message"]["content"], hits)
    result = {
        "answer": text,
        "sources": urls,
        "retrieved": [c["id"] for c in first_hits],
        "scores": [c["score"] for c in first_hits],
        "answerable": ok,
        "check": check,
        "cached": False,
        "agent": retry,
        "search_seconds": round(searched - start, 2),
        "check_seconds": round(checked - searched, 2),
        "agent_seconds": round(retried - checked, 2) if retry else None,
        "answer_seconds": round(time.perf_counter() - retried, 2) if ok else None,
        "prompt_tokens": sum(c["prompt_tokens"] for c in calls),
        "output_tokens": sum(c["output_tokens"] for c in calls),
        "calls": calls,
    }
    if use_cache:
        remember(vector, key, question, result)
    yield "result", result


def main():
    result = answer(" ".join(sys.argv[1:]))
    print(result["answer"])
    if result["sources"]:
        print("\nSources:")
        for url in result["sources"]:
            print(f"  {url}")
    seconds = sum(result[k] or 0 for k in ("search_seconds", "check_seconds", "answer_seconds"))
    print(f"\n{'from cache, ' if result['cached'] else ''}{seconds:.1f}s")


if __name__ == "__main__":
    main()
