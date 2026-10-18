"""HealthVer three-label validation is independent of runtime model predictions."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.evaluation.healthver_nli import (
    GOLD_MAP,
    PRED_MAP,
    bootstrap,
    classify_decision_origin,
    label_diagnostics,
    read_rows,
    selective,
    three_way,
    topic_diagnostics,
)


def test_3way_confusion_and_macro_f1():
    true = ["SUPPORT", "REFUTE", "NEUTRAL", "NEUTRAL"]
    pred = ["SUPPORT", "NEUTRAL", "NEUTRAL", "REFUTE"]
    m = three_way(true, pred)
    assert m["count"] == 4
    assert m["accuracy"] == 0.5
    assert m["confusion"]["REFUTE"]["NEUTRAL"] == 1
    assert m["per_class"]["SUPPORT"]["f1"] == 1.0
    assert m["per_class"]["REFUTE"]["recall"] == 0.0
    assert abs(m["per_class"]["NEUTRAL"]["f1"] - .5) < 1e-10
    assert m["balanced_accuracy"] == .5
    assert abs(m["macro_f1"] - .5) < 1e-10


def test_known_healthver_neutral_is_measured_not_concealed():
    assert set(GOLD_MAP.values()) == {"SUPPORT", "REFUTE", "NEUTRAL"}
    assert PRED_MAP["INSUFFICIENT_MODEL_EVIDENCE"] == "NEUTRAL"
    measured = selective(["SUPPORT", "REFUTE", "NEUTRAL"],
                         ["SUPPORT", "NEUTRAL", "NEUTRAL"])
    assert measured["non_neutral_coverage"] == 1 / 3
    assert measured["accuracy_given_non_neutral_prediction"] == 1.0
    assert measured["neutral_class_correct_out_of_all"] == 1 / 3
    none = selective(["REFUTE"], ["NEUTRAL"])
    assert none["accuracy_given_non_neutral_prediction"] is None


def test_strict_gold_protocol_rejects_bad_counts_labels_and_unknowns():
    with pytest.raises(ValueError):
        three_way([], [])
    with pytest.raises(ValueError):
        three_way(["SUPPORT"], [])
    with pytest.raises(ValueError):
        three_way(["UNKNOWN"], ["SUPPORT"])
    with pytest.raises(ValueError):
        bootstrap(["SUPPORT"], ["NEUTRAL"], [], 500)


def test_fixed_seed_cluster_bootstrap():
    gold = ["SUPPORT", "SUPPORT", "REFUTE", "NEUTRAL"]
    pred = ["SUPPORT", "NEUTRAL", "REFUTE", "REFUTE"]
    ids = ["claim1", "claim1", "claim2", "claim3"]
    first = bootstrap(gold, pred, ids)
    assert first == bootstrap(gold, pred, ids)
    assert 0 <= first["macro_f1"][0] <= first["macro_f1"][1] <= 1


def test_missing_or_modified_external_data_fails_closed(tmp_path):
    with pytest.raises(FileNotFoundError):
        read_rows(tmp_path, "test")
    (tmp_path / "healthver_test.csv").write_text("claim,evidence,label\nX,Y,Neutral\n")
    with pytest.raises(ValueError, match="SHA-256"):
        read_rows(tmp_path, "test")


def test_saved_external_results_confirm_all_three_gold_classes():
    report = json.loads((Path(__file__).resolve().parents[1] /
                         "reports/evaluation/healthver_test.json").read_text())
    assert report["split"]["test_rows"] == 1823
    assert report["split"]["unique_test_pairs"] == 1694
    assert report["split"]["train_test_exact_claim_overlaps"] == 1
    assert report["test_metrics_all_rows"]["count"] == 1823
    assert set(report["test_metrics_all_rows"]["label_distribution"]) == {
        "SUPPORT", "REFUTE", "NEUTRAL"
    }
    assert report["model_fitted_on_healthver"] is False
    assert report["test_label_based_threshold_selection"] is False
    assert report["test_metrics_all_rows"]["accuracy"] <= 1
    assert report["test_metrics_all_rows"]["macro_f1"] <= 1
    assert report["test_metrics_all_rows"]["per_class"]["NEUTRAL"]["recall"] <= 1
    assert report["deduplicated_test_metrics"]["count"] == 1694
    assert report["model_weights_sha256"].startswith("ebc79588")
    origins = report["neutral_and_abstention_diagnostics"]["decision_origin"]
    assert sum(item["count"] for item in origins.values()) == 1823
    assert origins["neutral_argmax"]["count"] == 1447
    assert origins["directional_below_threshold"]["count"] == 29
    assert origins["directional_below_margin"]["count"] == 0
    assert origins["directional_decision"]["count"] == 347
    assert origins["neutral_argmax"]["gold_distribution"]["SUPPORT"] == 540
    assert origins["neutral_argmax"]["gold_distribution"]["REFUTE"] == 269
    all_metrics = report["test_metrics_all_rows"]
    raw = report["neutral_and_abstention_diagnostics"][
        "argmax_three_class_metrics_without_abstention_mapping"]
    assert raw["accuracy"] > all_metrics["accuracy"]
    assert report["neutral_and_abstention_diagnostics"][
        "expected_calibration_error_10_bins_descriptive"] > .45
    assert sum(item["n"] for item in
               report["neutral_and_abstention_diagnostics"]["confidence_bins"]) == 1823
    subgroup = report["topic_stratified_exploratory"]
    assert len(subgroup["included"]) == 19
    assert all(row["n"] >= 30 for row in subgroup["included"].values())
    assert report["exact_train_claim_overlap_excluded_sensitivity"]["count"] == 1817



def test_neutral_vs_uncertain_directional_abstention_is_separated():
    scores = [
        {"entailment": .85, "contradiction": .06, "neutral": .09},
        {"entailment": .60, "contradiction": .20, "neutral": .20},
        {"entailment": .10, "contradiction": .09, "neutral": .81},
        {"entailment": .05, "contradiction": .80, "neutral": .15},
    ]
    gold = ["SUPPORT", "SUPPORT", "NEUTRAL", "REFUTE"]
    pred = ["SUPPORT", "NEUTRAL", "NEUTRAL", "REFUTE"]
    out = label_diagnostics(gold, scores, pred)
    reasons = out["decision_origin"]
    assert reasons["neutral_argmax"]["count"] == 1
    assert reasons["directional_below_threshold"]["count"] == 1
    assert reasons["directional_decision"]["count"] == 2
    assert reasons["directional_below_margin"]["count"] == 0
    assert reasons["directional_below_threshold"]["gold_distribution"]["SUPPORT"] == 1
    assert out["argmax_three_class_metrics_without_abstention_mapping"]["accuracy"] == 1.0
    assert 0 <= out["expected_calibration_error_10_bins_descriptive"] <= 1
    assert 0 <= out["brier_score_multiclass_uncalibrated"] <= 2
    assert sum(b["n"] for b in out["confidence_bins"]) == 4
    assert len(out["confidence_bins"]) == 10


def test_margin_inactive_at_fixed_frozen_threshold():
    # Since max >=0.70, runner-up <=0.30, so score margin >=0.40>0.15.
    assert classify_decision_origin({
        "entailment": .70, "contradiction": .30, "neutral": 0.0
    }) == "directional_decision"
    assert classify_decision_origin({
        "entailment": .35, "contradiction": .33, "neutral": .32
    }) == "directional_below_threshold"


def test_diagnostics_fail_closed_if_prediction_mismatch():
    with pytest.raises(ValueError, match="align"):
        label_diagnostics([], [], [])
    with pytest.raises(ValueError, match="diverges"):
        label_diagnostics(
            ["SUPPORT"],
            [{"entailment": .90, "contradiction": .05, "neutral": .05}],
            ["NEUTRAL"],
        )
    with pytest.raises(ValueError, match="finite three-label"):
        label_diagnostics(
            ["NEUTRAL"],
            [{"entailment": .15, "contradiction": .10}],
            ["NEUTRAL"],
        )


def test_topic_exploratory_aggregation_minimum_and_privacy_threshold():
    rows = [{"topic_ip": "A"}] * 3 + [{"topic_ip": "B"}]
    gold = ["SUPPORT", "REFUTE", "NEUTRAL", "SUPPORT"]
    pred = ["SUPPORT", "NEUTRAL", "NEUTRAL", "NEUTRAL"]
    out = topic_diagnostics(rows, gold, pred, minimum=3)
    assert out["included"]["A"]["n"] == 3
    assert out["included"]["A"]["support_recall"] == 1.0
    assert out["suppressed_topic_counts"] == {"B": 1}
    with pytest.raises(ValueError, match="Topic vectors"):
        topic_diagnostics(rows[:1], gold, pred)
