"""Synthetic-only regressions for paired retrieval + evidence-quality evaluation."""
from __future__ import annotations

import copy
import hashlib
import json
import sys

import pytest

from literature_evidence_mcp.dual_track_audit import audit_dual_track
from scripts.evaluation import dual_track_head_to_head as cli


def fixture():
    gold = {
        "retrieval": [
            {"id": "q1", "known_positive_ids": ["a", "b"]},
            {"id": "q2", "known_positive_ids": ["c"]},
            {"id": "q3", "known_positive_ids": []},
        ],
        "classification": [
            {"id": "c1", "label": "SUPPORT"},
            {"id": "c2", "label": "REFUTE"},
            {"id": "c3", "label": "INSUFFICIENT"},
            {"id": "c4", "label": "SUPPORT"},
        ],
    }
    systems = {
        "ours": {
            "retrieval": [
                {"id": "q1", "status": "OK", "ranked_ids": ["a", "x", "b"]},
                {"id": "q2", "status": "PARTIAL", "ranked_ids": ["z"]},
                {"id": "q3", "status": "BLOCKED", "ranked_ids": []},
            ],
            "classification": [
                {"id": "c1", "prediction": "SUPPORT"},
                {"id": "c2", "prediction": "MIXED"},
                {"id": "c3", "prediction": "INSUFFICIENT"},
                {"id": "c4", "prediction": "ERROR"},
            ],
        },
        "competitor": {
            "retrieval": [
                {"id": "q1", "status": "OK", "ranked_ids": ["x", "b"]},
                {"id": "q2", "status": "OK", "ranked_ids": ["c"]},
                {"id": "q3", "status": "ERROR", "ranked_ids": []},
            ],
            "classification": [
                {"id": "c1", "prediction": "ABSTAIN"},
                {"id": "c2", "prediction": "REFUTE"},
                {"id": "c3", "prediction": "SUPPORT"},
                {"id": "c4", "prediction": "BLOCKED"},
            ],
        },
    }
    return gold, systems


def test_both_tracks_kept_separate_and_non_decisions_are_not_neutral():
    gold, systems = fixture()
    result = audit_dual_track(gold, systems)
    ours = result["retrieval"]["ours"]
    assert ours["queries_total"] == 3
    assert ours["queries_scored"] == 2
    assert ours["queries_without_known_positive"] == 1
    assert ours["known_positive_recall_at_k"] == {"1": 0.25, "5": 0.5, "10": 0.5}
    assert ours["mrr_first_known_positive"] == 0.5
    assert ours["precision_at_k"] is None and ours["false_positive_rate"] is None
    assert ours["state_counts"] == {"OK": 1, "PARTIAL": 1, "NULL": 0, "BLOCKED": 1, "ERROR": 0}
    cls = result["classification"]["ours"]
    assert cls["cases_total"] == 4 and cls["decided"] == 2
    assert cls["decision_coverage"] == 0.5
    assert cls["accuracy_all_cases"] == 0.5
    assert cls["selective_accuracy"] == 1
    assert cls["confusion"]["REFUTE"]["MIXED"] == 1
    assert cls["confusion"]["SUPPORT"]["ERROR"] == 1
    assert cls["confusion"]["INSUFFICIENT"]["INSUFFICIENT"] == 1
    assert cls["non_decisions_are_not_neutral"]
    assert result["primary_metric_selected"] is False
    assert result["blinded_evaluation_verified"] is False
    assert result["competitor_executions_verified"] is False
    assert not result["significance_test_performed"]
    assert result["status"].startswith("DESCRIPTIVE")
    assert "ours__versus__competitor" not in result["paired_descriptive_deltas"]["retrieval"]
    assert "competitor__versus__ours" in result["paired_descriptive_deltas"]["retrieval"]


@pytest.mark.parametrize("change", [
    lambda g, s: g.update({"other": []}),
    lambda g, s: g.pop("retrieval"),
    lambda g, s: s.pop("competitor"),
    lambda g, s: s["ours"].pop("retrieval"),
    lambda g, s: s["ours"]["retrieval"].pop(),
    lambda g, s: s["ours"]["classification"][0].update(id="wrong"),
    lambda g, s: g["retrieval"].append(copy.deepcopy(g["retrieval"][0])),
    lambda g, s: g["classification"][0].update(id=""),
    lambda g, s: g["classification"][0].update(id="x" * 251),
    lambda g, s: g["retrieval"][0].update(known_positive_ids=[1]),
    lambda g, s: g["retrieval"][0].update(known_positive_ids=["a", "a"]),
    lambda g, s: s["ours"]["retrieval"][0].update(ranked_ids=["a", "a"]),
    lambda g, s: s["ours"]["retrieval"][0].update(ranked_ids=[""]),
    lambda g, s: s["ours"]["retrieval"][0].update(ranked_ids=None),
    lambda g, s: s["ours"]["retrieval"][0].update(status="OPEN"),
    lambda g, s: s["ours"]["retrieval"][2].update(ranked_ids=["a"]),
    lambda g, s: g["classification"][0].update(label="UNKNOWN"),
    lambda g, s: s["ours"]["classification"][0].update(prediction="UNKNOWN"),
    lambda g, s: g["retrieval"][0].update(known_positive_ids="a"),
    lambda g, s: s["ours"]["retrieval"][0].update(status=None),
    lambda g, s: g["retrieval"].append(5),
    lambda g, s: s["ours"]["classification"][0].update(id=0),
    lambda g, s: s.update({"": s.pop("competitor")}),
])
def test_all_malformed_or_misaligned_inputs_rejected(change):
    gold, systems = fixture()
    change(gold, systems)
    with pytest.raises((ValueError, TypeError)):
        audit_dual_track(gold, systems)


@pytest.mark.parametrize("bad_gold,bad_systems", [
    (None, {}), ({}, None), (None, None),
])
def test_wrong_top_level_types_fail(bad_gold, bad_systems):
    with pytest.raises(TypeError):
        audit_dual_track(bad_gold, bad_systems)


def test_unscored_retrieval_never_invents_relevance_precision_and_zero_decisions():
    gold, systems = fixture()
    for record in gold["retrieval"]:
        record["known_positive_ids"] = []
    for name in systems:
        for item in systems[name]["classification"]:
            item["prediction"] = "ABSTAIN"
    report = audit_dual_track(gold, systems)
    r = report["retrieval"]["ours"]
    assert r["known_positive_recall_at_k"] == {"1": None, "5": None, "10": None}
    assert r["mrr_first_known_positive"] is None
    assert report["paired_descriptive_deltas"]["retrieval"]["competitor__versus__ours"][
        "known_positive_recall_at_1_delta"
    ] is None
    c = report["classification"]["ours"]
    assert c["decision_coverage"] == 0 and c["selective_accuracy"] is None
    assert c["accuracy_all_cases"] == 0


def test_class_without_gold_support_has_undefined_recall_and_f1():
    gold, systems = fixture()
    for row in gold["classification"]:
        row["label"] = "SUPPORT"
    for group in systems.values():
        for row in group["classification"]:
            row["prediction"] = "ABSTAIN"
    result = audit_dual_track(gold, systems)
    metric = result["classification"]["ours"]
    assert metric["per_class_recall"]["REFUTE"] is None
    assert metric["per_class_f1"]["INSUFFICIENT"] is None
    assert metric["macro_f1"] == 0


def _write_sealed_inputs(tmp_path):
    gold, systems = fixture()
    goldpath = tmp_path / "gold.json"
    outpath = tmp_path / "outputs.json"
    manifestpath = tmp_path / "manifest.json"
    goldpath.write_text(json.dumps(gold))
    outpath.write_text(json.dumps(systems))
    manifestpath.write_text(json.dumps({
        "gold_sha256": hashlib.sha256(goldpath.read_bytes()).hexdigest(),
        "outputs_sha256": hashlib.sha256(outpath.read_bytes()).hexdigest(),
        "dataset_reference": "synthetic only; no clinical meaning",
        "evaluation_reference": "unverified scripted baseline",
    }))
    return manifestpath, goldpath, outpath


def test_pinned_manifest_evaluates_without_any_per_case_leak(tmp_path):
    args = _write_sealed_inputs(tmp_path)
    result = cli.evaluate_files(*args)
    assert result["frozen_inputs"]["integrity_verified"]
    assert result["frozen_inputs"]["independent_authority_authenticated"] is False
    assert '"q1"' not in json.dumps(result)
    assert '"c1"' not in json.dumps(result)
    assert result["classification"]["ours"]["cases_total"] == 4


@pytest.mark.parametrize("change", [
    lambda m: m.pop("gold_sha256"),
    lambda m: m.update(outputs_sha256="invalid"),
    lambda m: m.update(dataset_reference=""),
    lambda m: m.update(evaluation_reference="a" * 301),
])
def test_manifest_missing_pin_and_unsafe_reference_rejected(tmp_path, change):
    manifest, gold, outputs = _write_sealed_inputs(tmp_path)
    obj = json.loads(manifest.read_text())
    change(obj)
    manifest.write_text(json.dumps(obj))
    with pytest.raises(ValueError):
        cli.evaluate_files(manifest, gold, outputs)


def test_modified_gold_or_predictions_fail_closed(tmp_path):
    manifest, gold, outputs = _write_sealed_inputs(tmp_path)
    gold.write_text(gold.read_text() + " ")
    with pytest.raises(ValueError, match="SHA-256"):
        cli.evaluate_files(manifest, gold, outputs)
    _, gold, outputs = _write_sealed_inputs(tmp_path)
    outputs.write_text(outputs.read_text() + " ")
    with pytest.raises(ValueError, match="SHA-256"):
        cli.evaluate_files(manifest, gold, outputs)


def test_main_cli_writes_only_aggregate_report(tmp_path, monkeypatch, capsys):
    manifest, gold, outputs = _write_sealed_inputs(tmp_path)
    report = tmp_path / "dir" / "report.json"
    monkeypatch.setattr(sys, "argv", ["script", "--manifest", str(manifest),
                        "--gold", str(gold), "--outputs", str(outputs),
                        "--report", str(report)])
    cli.main()
    result = json.loads(report.read_text())
    assert result["status"].startswith("DESCRIPTIVE_TWO_TRACK")
    assert "synthetic only" in result["frozen_inputs"]["dataset_reference"]
    assert "no scientific winner" in capsys.readouterr().out


def test_empty_gold_track_is_rejected():
    gold, systems = fixture()
    gold["retrieval"] = []
    with pytest.raises(ValueError, match="nonempty"):
        audit_dual_track(gold, systems)


def test_null_and_blocked_are_distinct_not_scientific_negatives():
    gold, systems = fixture()
    systems["ours"]["retrieval"][2]["status"] = "NULL"
    systems["ours"]["classification"][2]["prediction"] = "NULL"
    result = audit_dual_track(gold, systems)
    assert result["retrieval"]["ours"]["state_counts"]["NULL"] == 1
    assert result["classification"]["ours"]["confusion"]["INSUFFICIENT"]["NULL"] == 1
    assert result["classification"]["ours"]["accuracy_all_cases"] == 0.25
    assert result["classification"]["ours"]["decided"] == 1


def test_null_search_cannot_claim_document_results():
    gold, systems = fixture()
    systems["ours"]["retrieval"][0]["status"] = "NULL"
    with pytest.raises(ValueError, match="failed retrieval"):
        audit_dual_track(gold, systems)
