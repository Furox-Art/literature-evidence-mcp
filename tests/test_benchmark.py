"""Tests exercise external benchmark scoring without embedding third-party data."""
import pytest

from literature_evidence_mcp.benchmark import compute_metrics, load_records


def test_benchmark_aggregates_and_abstains():
    rows = [
        {"paper_id": "a", "body": "The enrolled patients were randomly assigned.",
         "fragments": ["patients were randomly assigned"]},
        {"paper_id": "b", "body": "Separate article with unrelated outcome.",
         "fragments": ["unrelated outcome"]},
    ]
    result = compute_metrics(rows)
    assert result["evaluated_papers"] == 2
    assert result["quoted_excerpts"] == 2
    assert result["direct_match_fraction"] == 1.0
    assert result["cross_paper_false_match_fraction"] == 0
    assert result["independent_scientific_risk_of_bias_accuracy"] == "NOT_EVALUATED"


def test_benchmark_refuses_mutable_or_wrong_external_dataset(tmp_path):
    p = tmp_path / "unknown.csv"
    p.write_text("unlicensed, unpinned data")
    with pytest.raises(ValueError, match="SHA-256"):
        load_records(p)


def test_benchmark_empty_case_is_explicit_unknown():
    result = compute_metrics([])
    assert result["direct_match_fraction"] is None
    assert result["cross_paper_false_match_fraction"] is None
