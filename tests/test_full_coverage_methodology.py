"""Strict method, source, and benchmark negative-path tests."""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from literature_evidence_mcp import benchmark
from literature_evidence_mcp.methodology import (
    _locate,
    audit_methodology_evidence,
    audit_statistical_fields,
)
from literature_evidence_mcp.source_audit import audit_pmc_paragraph_evidence

SOURCE = "A random allocation was performed. The protocol was prespecified."


def audit(annotations=None, *, text=SOURCE, design="randomized_trial"):
    return audit_methodology_evidence("paper", "endpoint", design,
                                      text, annotations or [])


def note(domain, answer, quote=""):
    return {"domain": domain, "answer": answer, "quote": quote}


def pmc(paragraph="A random allocation was performed."):
    return {"pmcid": "PMC14", "sha256_xml": "f" * 64,
            "spans": [{"text": paragraph, "span_id": "PMC14:p1",
                       "section": "Methods", "paragraph_index": 1,
                       "sha256_text": hashlib.sha256(paragraph.encode()).hexdigest()}],
            "truncated": False}


def test_locator_missing_and_reporting_input_limits():
    assert _locate("source", " ") is None
    for kwargs in [
        {"study_id": None}, {"outcome": None}, {"study_design": "other"},
        {"source_text": ""}, {"source_text": "x" * 250001},
        {"annotations": [None]}, {"annotations": [{"domain": "bad", "answer": "unclear"}]},
        {"annotations": [note("sequence_generation", "reported_yes", "x" * 2501)]},
    ]:
        data = {"study_id": "source", "outcome": "endpoint",
                "study_design": "randomized_trial", "source_text": SOURCE,
                "annotations": []}
        data.update(kwargs)
        with pytest.raises((TypeError, ValueError)):
            audit_methodology_evidence(**data)


def test_method_not_applicable_and_optional_explanation():
    out = audit([note("sequence_generation", "not_applicable")])
    assert out["domains"]["sequence_generation"]["status"] == (
        "NOT_APPLICABLE_USER_REPORTED")
    other = audit([note("sequence_generation", "unclear",
                        "random allocation was performed")])
    assert other["domains"]["sequence_generation"]["annotations"][0][
        "source_match"] is True
    assert other["domains"]["sequence_generation"]["status"] == "UNKNOWN"


def test_method_bad_statistics_cases():
    with pytest.raises(ValueError):
        audit_statistical_fields([])
    with pytest.raises(TypeError):
        audit_statistical_fields([None])
    out = audit_statistical_fields([{"ci_lower": 1}, {"ci_lower": 3,
                                 "ci_upper": 2}, {"p_value": 2}])
    assert "PARTIAL_CONFIDENCE_INTERVAL" in out["records"][0]["flags"]


@pytest.mark.parametrize("changed,error", [
    ({"pmcid": 1}, "retrieved"),
    ({"sha256_xml": ""}, "provenance"),
    ({"spans": None}, "paragraph spans"),
    ({"spans": [None]}, "paragraph record"),
    ({"spans": []}, "No extractable"),
])
def test_source_audit_invalid_primary_source(changed, error):
    source = pmc()
    source.update(changed)
    with pytest.raises((ValueError, TypeError), match=error):
        audit_pmc_paragraph_evidence(source, "Outcome", "randomized_trial", [])


def test_source_overlimit_and_not_applicable():
    large = "x" * 250001
    source = pmc(large)
    with pytest.raises(ValueError, match="exceeds"):
        audit_pmc_paragraph_evidence(source, "Outcome", "randomized_trial", [])
    done = audit_pmc_paragraph_evidence(
        pmc(), "Outcome", "randomized_trial",
        [note("sequence_generation", "not_applicable")])
    assert done["domains"]["sequence_generation"]["status"] == (
        "NOT_APPLICABLE_USER_REPORTED")


def test_source_empty_short_match_guard():
    result = audit_pmc_paragraph_evidence(
        pmc(), "Outcome", "randomized_trial",
        [note("sequence_generation", "reported_yes", "A random")])
    assert not result["domains"]["sequence_generation"]["annotations"][0][
        "source_match"]
    assert result["untraceable_domain_count"] == 1


def test_benchmark_excludes_too_short_quoted_fragments(tmp_path, monkeypatch):
    import csv
    import json
    path = tmp_path / "tiny.csv"
    record = {
        "paper_id": "p1",
        "paper_parse": json.dumps({"pdf_parse": {"body_text": [
            {"text": "Small text is insufficient."}]}}),
        "manual_assessment": json.dumps([{"result": [{
            "rationale_text_quote": 'Reviewer said "small text" and discussed implications.'}]}]),
        "roboto2_assessment": "null",
    }
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=record.keys())
        writer.writeheader()
        writer.writerow(record)
    monkeypatch.setattr(benchmark, "DATA_SHA256",
                        hashlib.sha256(path.read_bytes()).hexdigest())
    assert benchmark.load_records(path) == []


def test_benchmark_main_guard_executes_with_pinned_fixture(tmp_path, monkeypatch):
    """Execute the real CLI guard using a run_path and pinned synthetic CSV."""
    import csv
    import runpy
    import sys

    fixture = tmp_path / "simple.csv"
    sample = {"paper_id": "one", "paper_parse": "null",
              "manual_assessment": "[]", "roboto2_assessment": "null"}
    with fixture.open("w", newline="") as out:
        wr = csv.DictWriter(out, fieldnames=sample)
        wr.writeheader()
        wr.writerow(sample)
    monkeypatch.setattr(benchmark, "DATA_SHA256",
                        hashlib.sha256(fixture.read_bytes()).hexdigest())
    monkeypatch.setattr(sys, "argv", ["script", str(fixture)])
    # run_path imports a fresh module, so its real pinned digest intentionally rejects this fixture.
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        runpy.run_path(str(Path(benchmark.__file__)), run_name="__main__")
