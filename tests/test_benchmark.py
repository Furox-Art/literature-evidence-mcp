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


def test_benchmark_parser_on_pin_checked_synthetic_fixture(tmp_path, monkeypatch):
    """No third-party raw dataset included; synthetic fixture exercises I/O."""
    import csv
    import hashlib
    import json

    from literature_evidence_mcp import benchmark
    fixture = tmp_path / "fixture.csv"
    fields = ["paper_id", "paper_parse", "manual_assessment", "roboto2_assessment"]
    quote = "The treatment group response differed substantially"
    rows = [
        {
            "paper_id": "case1",
            "paper_parse": json.dumps({
                "pdf_parse": {"body_text": [{"text":
                    f"{quote} from the control group."}]} }),
            "manual_assessment": json.dumps([{"result": [{
                "rationale_text_quote": 'Expert summary: "' + quote +
                                        '" observed in passage.'}]}]),
            "roboto2_assessment": "null",
        },
        {
            "paper_id": "case2",
            "paper_parse": "null",
            "manual_assessment": json.dumps([{"result": []}]),
            "roboto2_assessment": "null",
        },
        {
            "paper_id": "case3",
            "paper_parse": json.dumps({"pdf_parse": {"body_text": []}}),
            "manual_assessment": json.dumps([{"result": []}]),
            "roboto2_assessment": "null",
        },
        {
            "paper_id": "case4",
            "paper_parse": json.dumps({"pdf_parse": {"body_text": [
                {"text": "Only synthetic and unquoted reviewer commentary."}]}}),
            "manual_assessment": json.dumps([{"result": [{
                "rationale_text_quote": "A reviewer paraphrase, not a direct quote."
            }]}]),
            "roboto2_assessment": "null",
        },
    ]
    with fixture.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    monkeypatch.setattr(
        benchmark, "DATA_SHA256", hashlib.sha256(fixture.read_bytes()).hexdigest(),
    )
    records = benchmark.load_records(fixture)
    assert len(records) == 1
    metrics = benchmark.compute_metrics(records)
    assert metrics["direct_match_fraction"] == 1.0
    assert metrics["cross_paper_false_match_fraction"] is None


def test_external_benchmark_cli_synthetic_only(tmp_path, monkeypatch, capsys):
    import hashlib
    import json
    import sys

    from literature_evidence_mcp import benchmark
    p = tmp_path / "data.csv"
    p.write_text(
        "paper_id,paper_parse,manual_assessment,roboto2_assessment\\n"
        "1,null,[],null\\n"
    )
    monkeypatch.setattr(
        benchmark, "DATA_SHA256", hashlib.sha256(p.read_bytes()).hexdigest(),
    )
    out = tmp_path / "report.json"
    monkeypatch.setattr(sys, "argv", ["benchmark", str(p), "--output", str(out)])
    benchmark.main()
    report = json.loads(out.read_text())
    assert report["evaluated_papers"] == 0
    assert report["independent_scientific_risk_of_bias_accuracy"] == "NOT_EVALUATED"
    assert "NOT_EVALUATED" in capsys.readouterr().out
