import json

from pinpoint_docs import answer as answer_module
from pinpoint_docs.answer import IDK, answer, parse, sources

HITS = [{"url": "https://a/"}, {"url": "https://b/"}, {"url": "https://a/"}]


def test_sources_keeps_only_real_excerpts_once():
    assert sources([2, 1, 3, 9, 0], HITS) == ["https://b/", "https://a/"]
    assert sources([], HITS) == []


def test_parse():
    code = 'EXCERPTS: 2, 9\nANSWER: Use `Query(description="x")`.'
    assert parse(code, HITS) == ('Use `Query(description="x")`.', ["https://b/"])
    assert parse(f"EXCERPTS: none\nANSWER: {IDK}", HITS) == (IDK, [])
    assert parse("EXCERPTS: 1\nANSWER: I don't know, maybe X.", HITS) == (IDK, [])
    assert parse("Sure! Here is the answer.", HITS) == (IDK, [])


def test_answer_keeps_only_links_found_in_the_excerpts():
    hits = [{"url": "https://fastapi.tiangolo.com/tutorial/body/", "text": "See https://docs.pydantic.dev/latest/."}]
    reply = "EXCERPTS: 1\nANSWER: Read https://docs.pydantic.dev/latest/ and http://evil.example/login now."
    text, urls = parse(reply, hits)
    assert text == "Read https://docs.pydantic.dev/latest/ and [link removed] now."
    assert urls == ["https://fastapi.tiangolo.com/tutorial/body/"]


def test_redact_hides_secrets_but_keeps_code():
    question = (
        "My key api_key=sk-12345 and token: abc fail, mail me at a.b@example.com. Using response_model_exclude_unset"
    )
    assert answer_module.redact(question) == (
        "My key api_key=[redacted] and token: [redacted] fail, mail me at [email] Using response_model_exclude_unset"
    )
    assert answer_module.redact("id 3f9a1c2b7d4e5f60718293a4b5c6d7e8 here") == "id [redacted] here"


def test_answer_logs_errors_instead_of_crashing(tmp_path, monkeypatch):
    def down(*args):
        raise ConnectionError("ollama is not running")

    monkeypatch.setattr(answer_module, "TRACES", tmp_path / "traces.jsonl")
    monkeypatch.setattr(answer_module, "respond", down)
    result = answer("How do I declare a body?")
    assert result["answer"] == IDK and result["sources"] == []
    assert result["error"] == "ConnectionError: ollama is not running"
    logged = json.loads((tmp_path / "traces.jsonl").read_text(encoding="utf-8"))
    assert logged["trace_id"] == result["trace_id"] and logged["question"] == "How do I declare a body?"


def test_cache_returns_only_near_identical_questions_with_the_same_settings(monkeypatch):
    import chromadb

    col = chromadb.EphemeralClient().get_or_create_collection(
        "test-answer-cache", configuration={"hnsw": {"space": "cosine"}}
    )
    monkeypatch.setattr(answer_module, "answer_cache", lambda: col)
    key = answer_module.settings_key("llama3.2", 5)
    assert answer_module.cached_answer([1.0, 0.0, 0.0], key) is None

    saved = {"answer": "Use a model.", "sources": ["https://a/"], "retrieved": ["tutorial/body.md#1"]}
    answer_module.remember([1.0, 0.0, 0.0], key, "How do I declare a body?", saved)
    assert answer_module.cached_answer([1.0, 0.01, 0.0], key) == saved
    assert answer_module.cached_answer([1.0, 0.5, 0.0], key) is None
    assert answer_module.cached_answer([1.0, 0.0, 0.0], answer_module.settings_key("qwen2.5:3b", 5)) is None
    assert answer_module.cached_answer([1.0, 0.0, 0.0], answer_module.settings_key("llama3.2", 10)) is None

    monkeypatch.setattr(answer_module, "SYSTEM", answer_module.SYSTEM + " Be brief.")
    assert answer_module.cached_answer([1.0, 0.0, 0.0], answer_module.settings_key("llama3.2", 5)) is None


HIT = {"id": "body#1", "url": "https://a/", "title": "Body", "section": "Body", "text": "Use a model.", "score": 0.03}


def streamed(*pieces):
    parts = [{"message": {"content": p}, "done": False} for p in pieces]
    return iter([*parts, {"message": {"content": ""}, "done": True, "prompt_eval_count": 10, "eval_count": 5}])


def fake_pipeline(monkeypatch, calls, *pieces):
    monkeypatch.setattr(answer_module, "embed_question", lambda q: [1.0, 0.0])
    monkeypatch.setattr(answer_module, "search", lambda q, k, vector: [HIT])

    def fake_chat(model, system, user, history=(), stream=False, **options):
        calls.append(system)
        return streamed(*pieces)

    monkeypatch.setattr(answer_module, "chat", fake_chat)


def test_no_check_skips_the_yes_no_call(monkeypatch):
    calls = []
    fake_pipeline(monkeypatch, calls, "EXCERPTS: 1\nANSWER: Use a model.")
    *_, (kind, result) = answer_module.respond("How do I declare a body?", 5, "llama3.2", use_cache=False, check=False)
    assert calls == [answer_module.SYSTEM]
    assert kind == "result" and result["answer"] == "Use a model." and result["check"] is False
    assert answer_module.settings_key("llama3.2", 5, check=False) != answer_module.settings_key("llama3.2", 5)


def test_only_the_answer_text_is_streamed(monkeypatch):
    fake_pipeline(monkeypatch, [], "EXCER", "PTS: 1\nANS", "WER: Use ", "a mod", "el.")
    events = list(answer_module.respond("How do I declare a body?", 5, "llama3.2", use_cache=False, check=False))
    tokens = [value for kind, value in events if kind == "token"]
    assert "".join(tokens) == "Use a model."
    assert events[-1][1]["sources"] == ["https://a/"]


def test_agent_searches_again_after_a_no(monkeypatch):
    other = {**HIT, "id": "other#1", "page": "other.md", "url": "https://other/", "text": "Something else."}
    body = {**HIT, "page": "tutorial/body.md"}
    monkeypatch.setattr(answer_module, "embed_question", lambda q: [1.0, 0.0])
    monkeypatch.setattr(
        answer_module, "search", lambda q, k, vector=None: [body] if q == "request body model" else [other]
    )
    verdicts = iter(["NO", "YES"])
    queries = []

    def fake_chat(model, system, user, history=(), stream=False, tools=None, **options):
        if tools:
            queries.append(user)
            call = {"function": {"name": "search_docs", "arguments": {"query": "request body model"}}}
            return {"message": {"content": "", "tool_calls": [call]}, "prompt_eval_count": 5, "eval_count": 5}
        if stream:
            return streamed("EXCERPTS: 1\nANSWER: Use a model.")
        return {"message": {"content": next(verdicts)}, "prompt_eval_count": 5, "eval_count": 1}

    monkeypatch.setattr(answer_module, "chat", fake_chat)
    question = "How do I declare a body?"
    *_, (_, result) = answer_module.respond(question, 3, "llama3.2", use_cache=False, agent=True)
    assert queries == [question]
    assert result["agent"] == {"query": "request body model", "retrieved": ["body#1"], "answerable": True}
    assert result["answer"] == "Use a model." and result["sources"] == ["https://a/"]
    assert result["retrieved"] == ["other#1"] and result["agent_seconds"] is not None
    assert [c["step"] for c in result["calls"]] == ["check", "agent", "check", "answer"]


def test_cancel_stops_the_answer_and_logs_it(tmp_path, monkeypatch):
    import threading

    fake_pipeline(monkeypatch, [], "EXCERPTS: 1\nANSWER: Use ", "a ", "model.")
    monkeypatch.setattr(answer_module, "TRACES", tmp_path / "traces.jsonl")
    cancel = threading.Event()
    seen = []
    for event in answer_module.answer_events("How do I declare a body?", use_cache=False, check=False, cancel=cancel):
        seen.append(event)
        if event[0] == "token":
            cancel.set()
    assert [kind for kind, _ in seen].count("token") == 1
    assert seen[-1][0] == "done" and seen[-1][1]["error"] == "cancelled"
    assert json.loads((tmp_path / "traces.jsonl").read_text(encoding="utf-8"))["error"] == "cancelled"
