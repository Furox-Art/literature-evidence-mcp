"""Fail-closed ranking protocol tests, independent of downloaded benchmark data."""
import pytest

from scripts.evaluation.scifact_open_retrieval import (
    metrics,
    paired_difference,
    percentile_interval,
    tokenize,
)


def test_gold_recall_and_rank_metrics():
    out = metrics([10, 30, 20, 40, 50], {20, 30})
    assert out["known_gold_recall_at_1"] == 0
    assert out["known_gold_recall_at_5"] == 1
    assert out["mrr_first_known_positive"] == .5
    assert 0 < out["known_gold_ndcg_at_10"] <= 1


def test_protocol_rejects_malformed_ranks():
    with pytest.raises(ValueError):
        metrics([1, 2], set())
    with pytest.raises(ValueError):
        metrics([1, 1], {1})


def test_utf8_tokenization_and_unknown_golds():
    assert tokenize("β-amyloid, MRI, neural") == ["amyloid", "mri", "neural"]
    assert metrics([1, 2], {333})["known_gold_recall_at_10"] == 0


def test_bootstrap_determinism_and_pairing():
    rows = [{"bm25": {"known_gold_recall_at_10": 1.0},
             "jaccard": {"known_gold_recall_at_10": 0.0}},
            {"bm25": {"known_gold_recall_at_10": 0.0},
             "jaccard": {"known_gold_recall_at_10": 1.0}}]
    first = paired_difference(rows, "bm25", "jaccard", "known_gold_recall_at_10")
    assert first == paired_difference(rows, "bm25", "jaccard", "known_gold_recall_at_10")
    assert first["mean"] == 0
    assert first["paired_query_bootstrap_95pct"][0] <= 0 <= first["paired_query_bootstrap_95pct"][1]
    with pytest.raises(ValueError):
        paired_difference([], "bm25", "jaccard", "known_gold_recall_at_10")


def test_percentile_bounds():
    assert percentile_interval([.5] * 500) == [.5, .5]
