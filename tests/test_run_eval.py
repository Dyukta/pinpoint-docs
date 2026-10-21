from pinpoint_docs.answer import IDK
from scripts.run_eval import grade, load_questions, sample

DOCS_Q = {"gold_pages": ["tutorial/body.md"]}
OTHER_Q = {"gold_pages": []}


def result(answer, sources=(), retrieved=("tutorial/body.md#1",)):
    return {"answer": answer, "sources": list(sources), "retrieved": list(retrieved)}


def test_grade_docs_question():
    cited = result("Use a model.", ["https://fastapi.tiangolo.com/tutorial/body/#declare-it"])
    assert grade(DOCS_Q, cited)["pass"]
    assert not grade(DOCS_Q, result("Use a model.", ["https://fastapi.tiangolo.com/tutorial/"]))["pass"]
    assert grade(DOCS_Q, result(IDK)) == {"said_idk": True, "search_found_gold": True, "cited_gold": False, "pass": False, "failure": "refused_with_gold"}
    assert grade(DOCS_Q, result(IDK, retrieved=["async.md#1"]))["failure"] == "search_missed_gold"
    assert grade(DOCS_Q, result("Use a model.", ["https://fastapi.tiangolo.com/async/"]))["failure"] == "cited_wrong_page"


def test_grade_other_question():
    assert grade(OTHER_Q, result(IDK)) == {"said_idk": True, "pass": True, "failure": None}
    assert grade(OTHER_Q, result("Try upgrading.", ["https://fastapi.tiangolo.com/"]))["failure"] == "answered_unanswerable"


def test_grade_error_always_fails():
    assert grade(OTHER_Q, {**result(IDK), "error": "URLError: refused"}) == {"said_idk": True, "pass": False, "failure": "error"}


def test_sample_is_fixed_and_balanced():
    a, b = sample(load_questions()), sample(load_questions())
    assert [q["id"] for q in a] == [q["id"] for q in b]
    assert sum(bool(q["gold_pages"]) for q in a) == 20 and len(a) == 40
