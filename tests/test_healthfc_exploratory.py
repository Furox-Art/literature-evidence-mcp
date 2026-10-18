"""No metric or publication claim from unreviewed transformed HealthFC text."""
from __future__ import annotations

import hashlib

import pytest

from scripts.evaluation import healthfc_controlled as transform
from scripts.evaluation import healthfc_exploratory as evaluation


def test_source_bytes_schema_and_rows_fail_closed(monkeypatch, tmp_path):
    path = tmp_path / "fixture.csv"
    path.write_text("en_claim,en_top_sentences,label\nSynthetic,Synthetic,0\n")
    monkeypatch.setattr(
        transform, "SOURCE_SHA256", hashlib.sha256(path.read_bytes()).hexdigest()
    )
    with pytest.raises(ValueError, match="source rows"):
        transform.read_source(path)
    path.write_text("claim,evidence,label\nSynthetic,Synthetic,0\n")
    monkeypatch.setattr(
        transform, "SOURCE_SHA256", hashlib.sha256(path.read_bytes()).hexdigest()
    )
    with pytest.raises(ValueError, match="columns missing"):
        transform.read_source(path)
    path.write_text("en_claim,en_top_sentences,label\nSynthetic,Synthetic,0\n")
    with pytest.raises(ValueError, match="SHA-256"):
        transform.read_source(path)


def test_frozen_cohort_fails_closed(monkeypatch, tmp_path):
    monkeypatch.setattr(evaluation, "read_source", lambda p: [])
    monkeypatch.setattr(evaluation, "prepare", lambda rows: ([], {
        "selected_rows": 0, "selected_label_distribution": {},
    }))
    with pytest.raises(ValueError, match="cohort changed"):
        evaluation.evaluate(tmp_path / "external.csv", {})


def test_model_selection_must_include_all_three(monkeypatch, tmp_path):
    records = [
        {"claim": "Synthetic hypothesis.", "evidence": "Synthetic text.",
         "label": "Neutral"},
    ]
    monkeypatch.setattr(evaluation, "read_source", lambda p: [])
    monkeypatch.setattr(evaluation, "prepare", lambda rows: (records, {
        "selected_rows": 1, "selected_label_distribution": {"NEUTRAL": 1},
    }))
    monkeypatch.setattr(evaluation, "FROZEN_COUNT", 1)
    monkeypatch.setattr(evaluation, "FROZEN_LABELS", {"NEUTRAL": 1})
    with pytest.raises(ValueError, match="3 fixed models"):
        evaluation.evaluate(tmp_path / "external.csv", {"unknown": tmp_path})


def test_aggregate_never_contains_licensed_rows(monkeypatch, tmp_path):
    payload = [
        {"claim": "Synthetic private text.", "evidence": "Private premise.",
         "label": "Supports"},
    ]
    monkeypatch.setattr(evaluation, "read_source", lambda p: [])
    monkeypatch.setattr(evaluation, "prepare", lambda rows: (payload, {
        "selected_rows": 1, "selected_label_distribution": {"SUPPORT": 1},
    }))
    monkeypatch.setattr(evaluation, "FROZEN_COUNT", 1)
    monkeypatch.setattr(evaluation, "FROZEN_LABELS", {"SUPPORT": 1})
    def fake_infer(folder, records, digest):
        assert records is payload
        return {"predictions": ["SUPPORT"], "raw_predictions": ["SUPPORT"],
                "metrics": {"accuracy": 1., "macro_f1": 1.0}}
    monkeypatch.setattr(evaluation, "infer_model", fake_infer)
    result = evaluation.evaluate(tmp_path / "corpus", {
        key: tmp_path / key for key in evaluation.CANDIDATES
    })
    assert result["status"].startswith("EXPLORATORY_")
    assert result["selection_policy"] == "NO_PRODUCTION_SELECTION_BASED_ON_EXPLORATORY_METRICS"
    assert "Private premise." not in repr(result)
    assert "Synthetic private text." not in repr(result)
    assert all("predictions" not in row and "raw_predictions" not in row
               for row in result["candidate_results"].values())
    assert len(result["paired_differences_vs_original"]) == 2
