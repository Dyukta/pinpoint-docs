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
    assert grade(DOCS_Q, result(IDK)) == {
        "said_idk": True,
        "search_found_gold": True,
        "cited_gold": False,
        "pass": False,
        "failure": "refused_with_gold",
    }
    assert grade(DOCS_Q, result(IDK, retrieved=["async.md#1"]))["failure"] == "search_missed_gold"
    assert (
        grade(DOCS_Q, result("Use a model.", ["https://fastapi.tiangolo.com/async/"]))["failure"] == "cited_wrong_page"
    )


def test_grade_other_question():
    assert grade(OTHER_Q, result(IDK)) == {"said_idk": True, "pass": True, "failure": None}
    assert (
        grade(OTHER_Q, result("Try upgrading.", ["https://fastapi.tiangolo.com/"]))["failure"]
        == "answered_unanswerable"
    )


def test_grade_error_always_fails():
    assert grade(OTHER_Q, {**result(IDK), "error": "URLError: refused"}) == {
        "said_idk": True,
        "pass": False,
        "failure": "error",
    }


def test_sample_is_fixed_and_balanced():
    a, b = sample(load_questions()), sample(load_questions())
    assert [q["id"] for q in a] == [q["id"] for q in b]
    assert sum(bool(q["gold_pages"]) for q in a) == 20 and len(a) == 40


def test_judge_verdict_parsing():
    from scripts.judge import agreement, verdict

    assert verdict("YES.") == "yes" and verdict(" partly, mostly") == "partly" and verdict("No") == "no"
    assert verdict("Maybe") == "unclear" and verdict("") == "unclear"
    assert agreement([("yes", "yes"), ("partly", "no"), ("no", "no")]) == "exact 2/3, yes vs not-yes 3/3"


def test_fresh_sample_never_uses_dev_or_test_questions():
    import json

    from scripts.run_eval import ROOT, fresh_sample

    split = json.loads((ROOT / "evals" / "split.json").read_text(encoding="utf-8"))
    questions, seed = fresh_sample(seed=7)
    assert seed == 7 and len(questions) == 40
    assert not {q["id"] for q in questions} & (set(split["dev"]) | set(split["test"]))
    assert {q["tag"] for q in questions} <= {"bug", "other-library"}
    assert fresh_sample(seed=7)[0] == questions


def test_trained_gate_separates_and_folds_stay_balanced():
    import numpy as np

    from scripts.train_gate import folds, probability, train

    rng = np.random.default_rng(0)
    x = np.vstack([rng.normal(1, 1, (30, 5)), rng.normal(-1, 1, (90, 5))])
    y = np.r_[np.ones(30), np.zeros(90)]
    p = probability(train(x, y), x)
    assert (p[:30] > 0.5).mean() > 0.9 and (p[30:] < 0.5).mean() > 0.9
    parts = folds(list(range(20)), [1] * 10 + [0] * 10)
    assert sorted(i for part in parts for i in part) == list(range(20))
    assert all(sum(i < 10 for i in part) == 2 for part in parts)
