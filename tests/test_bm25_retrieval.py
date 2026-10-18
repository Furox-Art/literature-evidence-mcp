"""Real BM25 integration and fail-closed optional dependency regression tests."""
from types import SimpleNamespace

import pytest

from literature_evidence_mcp import bm25_retrieval, server


DOCS = [
    {"id": "paper-3", "title": "Neural imaging", "abstract": "Magnetic resonance study."},
    {"id": "paper-2", "title": "Cardiac outcomes", "abstract": "The liver is unaffected."},
    {"id": "paper-1", "title": "Neural neural neural", "abstract": "Brain neural networks."},
]


def test_real_bm25_ranked_candidates_do_not_claim_scientific_truth():
    out = server.bm25_rank_evidence("neural networks", DOCS, 2)
    assert out["status"] == "BM25_LEXICAL_CANDIDATES_ONLY"
    assert out["candidate_count"] == 3
    assert out["lexically_matched_candidates"] == 2
    assert out["returned_count"] == 2
    assert out["results"][0]["id"] == "paper-1"
    assert out["semantic_support_verified"] is False
    assert out["source_authenticity_verified"] is False
    assert all(not result["scientific_support_verified"] for result in out["results"])
    assert all(len(result["supplied_text_sha256"]) == 64 for result in out["results"])


def test_real_bm25_ties_sorted_by_identifier_not_provider_order():
    corpus = [
        {"id": "z", "title": "brain study", "abstract": "brain study"},
        {"id": "a", "title": "brain study", "abstract": "brain study"},
        {"id": 42, "title": "liver study", "abstract": ""},
    ]
    out = bm25_retrieval.rank_supplied_evidence("brain", corpus, 1)
    assert out["results"][0]["id"] == "a"
    assert out["lexically_matched_candidates"] == 2


def test_no_lexical_overlap_or_indexable_corpus():
    none = server.bm25_rank_evidence("quantum", DOCS)
    assert none["status"] == "NO_QUERY_TERM_OVERLAP"
    assert none["returned_count"] == 0
    empty = server.bm25_rank_evidence("neural", [
        {"id": "punctuation", "title": "!?", "abstract": "?!"},
    ])
    assert empty["status"] == "NO_INDEXABLE_DOCUMENT_TEXT"
    assert not empty["semantic_support_verified"]


@pytest.mark.parametrize("query, documents, top_k, error", [
    (None, DOCS, 10, ValueError),
    ("x", DOCS, 10, ValueError),
    ("x" * 1001, DOCS, 10, ValueError),
    ("!!", DOCS, 10, ValueError),
    ("neural", DOCS, 0, ValueError),
    ("neural", DOCS, True, ValueError),
    ("neural", DOCS, 51, ValueError),
    ("neural", None, 10, ValueError),
    ("neural", [], 10, ValueError),
    ("neural", [{}] * 10001, 10, ValueError),
    ("neural", [None], 10, TypeError),
    ("neural", [{"id": None, "title": "neural"}], 10, ValueError),
    ("neural", [{"id": True, "title": "neural"}], 10, ValueError),
    ("neural", [{"id": "", "title": "neural"}], 10, ValueError),
    ("neural", [{"id": "x" * 257, "title": "neural"}], 10, ValueError),
    ("neural", [{"id": "x", "title": "neural"},
                {"id": "x", "title": "different"}], 10, ValueError),
    ("neural", [{"id": "x", "title": None, "abstract": "neural"}], 10, TypeError),
    ("neural", [{"id": "x", "abstract": 4}], 10, TypeError),
    ("neural", [{"id": "x", "title": "x" * 701}], 10, ValueError),
    ("neural", [{"id": "x", "abstract": "x" * 20001}], 10, ValueError),
    ("neural", [{"id": "x", "title": " ", "abstract": " "}], 10, ValueError),
])
def test_untrusted_inputs_fail_closed(query, documents, top_k, error):
    with pytest.raises(error):
        bm25_retrieval.rank_supplied_evidence(query, documents, top_k)


def test_total_payload_limit_rejects_large_corpus():
    corpus = [{"id": str(index), "abstract": "X" * 20000} for index in range(401)]
    with pytest.raises(ValueError, match="8MB"):
        server.bm25_rank_evidence("neural", corpus)


def test_missing_optional_dependency_returns_explicit_status(monkeypatch):
    original = bm25_retrieval.importlib.import_module

    def fake_import(name):
        if name == "rank_bm25":
            raise ModuleNotFoundError("rank-bm25 unavailable", name=name)
        return original(name)

    monkeypatch.setattr(bm25_retrieval.importlib, "import_module", fake_import)
    result = server.bm25_rank_evidence("neural", DOCS)
    assert result["status"] == "OPTIONAL_BM25_NOT_INSTALLED"
    assert result["install_extra"] == "literature-evidence-mcp[retrieval]"
    assert result["results"] == []
    assert result["semantic_support_verified"] is False


def test_nested_missing_dependency_is_not_mislabeled_as_optional(monkeypatch):
    def bad_import(name):
        raise ModuleNotFoundError("nested dependency absent", name="numpy")

    monkeypatch.setattr(bm25_retrieval.importlib, "import_module", bad_import)
    with pytest.raises(ModuleNotFoundError, match="nested"):
        server.bm25_rank_evidence("neural", DOCS)


def test_nonfinite_native_score_is_rejected(monkeypatch):
    class InvalidBM25:
        def __init__(self, corpus):
            self.corpus = corpus

        def get_scores(self, query):
            return [float("nan")] * len(self.corpus)

    fake = SimpleNamespace(BM25Okapi=InvalidBM25)
    monkeypatch.setattr(bm25_retrieval.importlib, "import_module", lambda _: fake)
    with pytest.raises(ValueError, match="non-finite"):
        server.bm25_rank_evidence("neural", DOCS)
