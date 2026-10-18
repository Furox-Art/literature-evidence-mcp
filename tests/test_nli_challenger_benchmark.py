"""No silent promotion of exploratory NLI candidates based on reused TEST labels."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.evaluation.nli_challenger_benchmark import (
    CANDIDATES,
    paired_claim_bootstrap,
    verify_class_labels,
    verify_weights,
)


def test_class_order_is_validated_not_assumed():
    assert verify_class_labels(SimpleNamespace(
        id2label={0: "entailment", 1: "neutral", 2: "contradiction"}
    )) == {0: "entailment", 1: "neutral", 2: "contradiction"}
    assert verify_class_labels(SimpleNamespace(
        id2label={"0": "contradiction", "1": "entailment", "2": "neutral"}
    )) == {0: "contradiction", 1: "entailment", 2: "neutral"}
    for mapping in [
        {0: "neutral", 1: "neutral", 2: "entailment"},
        {0: "LABEL_0", 1: "LABEL_1", 2: "LABEL_2"},
        {0: "contradiction", 2: "entailment", 3: "neutral"},
    ]:
        with pytest.raises(ValueError, match="class"):
            verify_class_labels(SimpleNamespace(id2label=mapping))


def test_candidate_has_pinned_revision_and_weight_hash():
    assert len(CANDIDATES) == 3
    for model in CANDIDATES.values():
        assert len(model["revision"]) == 40
        assert len(model["weights_sha256"]) == 64
        assert model["license"] in ("apache-2.0", "mit")


def test_pinned_model_fails_closed_if_missing_or_modified(tmp_path):
    with pytest.raises(FileNotFoundError):
        verify_weights(tmp_path)
    (tmp_path / "model.safetensors").write_bytes(b"mock")
    assert len(verify_weights(tmp_path)) == 64
    with pytest.raises(ValueError, match="SHA-256"):
        verify_weights(tmp_path, "0" * 64)


def test_paired_claim_bootstrap_keeps_clusters_intact_and_repeats():
    truth = ["SUPPORT", "SUPPORT", "REFUTE", "NEUTRAL"]
    first = ["SUPPORT", "REFUTE", "REFUTE", "NEUTRAL"]
    second = ["NEUTRAL", "NEUTRAL", "REFUTE", "SUPPORT"]
    claim = ["same", "same", "other", "third"]
    result = paired_claim_bootstrap(truth, first, second, claim, repeats=500)
    assert result["accuracy_difference"] == 0.5
    assert result == paired_claim_bootstrap(truth, first, second, claim)
    assert result["paired_claim_cluster_bootstrap_95pct"][0] <= .5
    assert result["paired_claim_cluster_bootstrap_95pct"][1] >= .5
    for data in [(truth, first, second, []), ([], [], [], [])]:
        with pytest.raises(ValueError, match="equal nonzero"):
            paired_claim_bootstrap(*data)


def test_external_exploratory_report_does_not_claim_model_selection():
    report = json.loads(
        (Path(__file__).resolve().parents[1] /
         "reports/evaluation/healthver_nli_paired_challengers.json").read_text()
    )
    assert report["test_size"] == 1823
    assert report["unique_test_pairs"] == 1694
    assert set(report["candidate_results"]) == set(CANDIDATES)
    assert "reused previously inspected TEST labels" in report["selection_disclaimer"]
    assert report["status"] == "EXPLORATORY_PINNED_MODEL_COMPARISON_NOT_PRODUCTION_SELECTION"
    for key, model in report["candidate_results"].items():
        assert model["candidate"]["revision"] == CANDIDATES[key]["revision"]
        assert model["candidate"]["weights_sha256"] == model["weights_sha256"]
        assert model["metrics"]["count"] == 1823
        assert model["unique_pair_metrics"]["count"] == 1694
        assert model["metrics"]["per_class"]["SUPPORT"]["recall"] <= 1
        assert 0 <= model["mean_multiclass_brier_score"] <= 2
    assert len(report["paired_differences_vs_frozen_production"]) == 2



def test_scifact_external_comparison_preserves_no_nei_gold():
    path = (Path(__file__).resolve().parents[1] /
            "reports/evaluation/scifact_nli_paired_challengers.json")
    report = json.loads(path.read_text())
    assert report["status"] == "EXPLORATORY_SCIFACT_GOLD_RATIONALE_NLI_COMPARISON"
    assert report["gold_rationales"] == 338
    assert set(report["candidate_results"]) == set(CANDIDATES)
    for item in report["candidate_results"].values():
        subset = item["scifact_gold_rationale_conditional"]
        assert subset["gold_rationales"] == 338
        assert subset["correct_decided"] <= subset["decided"] <= 338
        assert "NEUTRAL" not in item["metrics"]["label_distribution"]
    baseline = report["candidate_results"]["frozen_original_deberta_small"]
    assert baseline["scifact_gold_rationale_conditional"]["correct_decided"] == 110
