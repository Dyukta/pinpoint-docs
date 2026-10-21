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

    col = chromadb.EphemeralClient().get_or_create_collection("test-answer-cache", configuration={"hnsw": {"space": "cosine"}})
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
