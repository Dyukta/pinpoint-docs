import hashlib
import json
import re
import sys
import time
import uuid
from datetime import datetime, timezone
from functools import cache

import chromadb

from pinpoint_docs.index import CACHE, COLLECTION, DB, ROOT, ollama
from pinpoint_docs.search import embed_question, search

TRACES = ROOT / "data" / "traces.jsonl"
MODEL = "llama3.2"
IDK = "I don't know."
CACHE_DISTANCE = 0.03
EMPTY = {"answer": IDK, "sources": [], "retrieved": [], "scores": [], "answerable": False, "cached": False, "search_seconds": None, "check_seconds": None, "answer_seconds": None, "prompt_tokens": 0, "output_tokens": 0}
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
OPTIONS = {"temperature": 0, "num_ctx": 8192, "num_gpu": 99}
REPLY = re.compile(r"EXCERPTS:(.*?)\n\s*ANSWER:(.*)", re.S | re.I)


def sources(numbers, hits):
    return list(dict.fromkeys(hits[n - 1]["url"] for n in numbers if 1 <= n <= len(hits)))


def parse(reply, hits):
    match = REPLY.search(reply)
    if not match:
        return IDK, []
    urls = sources([int(n) for n in re.findall(r"\d+", match.group(1))], hits)
    text = match.group(2).strip()
    if not urls or "don't know" in text.lower():
        return IDK, []
    return text, urls


def excerpts(hits):
    return "\n\n".join(f"Excerpt {i} ({c['title']} > {c['section']}):\n{c['text']}" for i, c in enumerate(hits, 1))


def chat(model, system, user, **options):
    return ollama("/api/chat", {
        "model": model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "stream": False,
        "options": {**OPTIONS, **options},
    })


def is_answerable(question, context, model=MODEL):
    reply = chat(model, CHECK, f"Question:\n{question}\n\nExcerpts:\n\n{context}\n\n{CHECK_ASK}", num_predict=3)
    return reply["message"]["content"].strip().upper().startswith("YES"), reply


@cache
def answer_cache():
    return chromadb.PersistentClient(str(DB)).get_or_create_collection(CACHE, configuration={"hnsw": {"space": "cosine"}})


def settings_key(model, k, check=True):
    settings = [model, k, check, SYSTEM, CHECK, CHECK_ASK, OPTIONS, COLLECTION]
    return hashlib.sha256(json.dumps(settings, sort_keys=True).encode()).hexdigest()[:16]


def cached_answer(vector, key):
    hit = answer_cache().query(query_embeddings=[vector], n_results=1, where={"settings": key})
    if hit["ids"][0] and hit["distances"][0][0] <= CACHE_DISTANCE:
        meta = hit["metadatas"][0][0]
        return {"answer": meta["answer"], "sources": json.loads(meta["sources"]), "retrieved": json.loads(meta["retrieved"])}
    return None


def remember(vector, key, question, result):
    answer_cache().add(
        ids=[uuid.uuid4().hex],
        embeddings=[vector],
        documents=[question],
        metadatas=[{"settings": key, "answer": result["answer"], "sources": json.dumps(result["sources"]), "retrieved": json.dumps(result["retrieved"])}],
    )


def answer(question, k=5, model=MODEL, use_cache=True, check=True):
    trace = {"trace_id": uuid.uuid4().hex[:12], "time": datetime.now(timezone.utc).isoformat(timespec="seconds"), "model": model, "question": question}
    try:
        trace |= respond(question, k, model, use_cache, check)
        trace["error"] = None
    except Exception as e:
        trace |= {**EMPTY, "error": f"{type(e).__name__}: {e}"}
    with TRACES.open("a", encoding="utf-8") as f:
        f.write(json.dumps(trace, ensure_ascii=False) + "\n")
    return trace


def respond(question, k, model, use_cache, check=True):
    start = time.perf_counter()
    vector = embed_question(question)
    key = settings_key(model, k, check)
    hit = cached_answer(vector, key) if use_cache else None
    if hit:
        return {**EMPTY, **hit, "cached": True, "search_seconds": round(time.perf_counter() - start, 2)}
    hits = search(question, k, vector=vector)
    searched = time.perf_counter()
    context = excerpts(hits)
    ok, verdict = is_answerable(question, context, model) if check else (True, {})
    checked = time.perf_counter()
    calls = [verdict]
    text, urls = IDK, []
    if ok:
        reply = chat(model, SYSTEM, f"Question:\n{question}\n\nExcerpts:\n\n{context}")
        calls.append(reply)
        text, urls = parse(reply["message"]["content"], hits)
    result = {
        "answer": text,
        "sources": urls,
        "retrieved": [c["id"] for c in hits],
        "scores": [c["score"] for c in hits],
        "answerable": ok,
        "check": check,
        "cached": False,
        "search_seconds": round(searched - start, 2),
        "check_seconds": round(checked - searched, 2),
        "answer_seconds": round(time.perf_counter() - checked, 2) if ok else None,
        "prompt_tokens": sum(c.get("prompt_eval_count", 0) for c in calls),
        "output_tokens": sum(c.get("eval_count", 0) for c in calls),
    }
    if use_cache:
        remember(vector, key, question, result)
    return result


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
