from pinpoint_docs.search import BM25, mmr, rrf, tokenize


def test_tokenize():
    assert tokenize("Use response_model=Item!") == ["use", "response_model", "item"]


def test_bm25_ranks_matching_doc_first():
    bm25 = BM25(["cats and dogs", "request body with pydantic", "dogs only"])
    assert bm25.rank("pydantic body")[0] == 1
    assert bm25.rank("dogs") == [2, 0]
    assert bm25.rank("nothing here") == []


def test_rrf_rewards_agreement():
    assert rrf([["a", "b", "c"], ["b", "c", "a"]])[0][0] == "b"
    assert [i for i, _ in rrf([["a"], ["b"]])] == ["a", "b"]
    assert rrf([["a"]]) == [("a", 1 / 61)]


def test_mmr_skips_near_duplicates():
    import numpy as np

    query = np.array([1.0, 0.0])
    vectors = np.array([[0.98, 0.2], [0.97, 0.24], [0.6, 0.8]])
    assert mmr(query, vectors, k=2, weight=1.0) == [0, 1]
    assert mmr(query, vectors, k=2, weight=0.3) == [0, 2]
