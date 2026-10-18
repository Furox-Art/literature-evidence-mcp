"""HealthVer three-label validation is independent of runtime model predictions."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.evaluation.healthver_nli import (
    GOLD_MAP,
    PRED_MAP,
    bootstrap,
    read_rows,
    selective,
    three_way,
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
