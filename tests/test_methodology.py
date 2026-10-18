"""Regression suite for evidence traceability (no risk-of-bias ground-truth claims)."""
import pytest

from literature_evidence_mcp.methodology import (
    audit_methodology_evidence,
    audit_statistical_fields,
)

TEXT = (
    "Participants were randomly assigned using computer generated numbers. "
    "Allocation was concealed using sealed envelopes. "
    "The report does not describe outcome blinding. "
    "The primary endpoint was reported with a prespecified analysis plan. "
)


def annotate(domain, answer="reported_yes", quote=""):
    return {"domain": domain, "answer": answer, "quote": quote}


def audit(records, text=TEXT, design="randomized_trial"):
    return audit_methodology_evidence("doi:10.1000/test", "Primary endpoint",
                                      design, text, records)


def test_traceable_direct_source_quote_and_offsets():
    q = "randomly assigned using computer generated numbers"
    out = audit([annotate("sequence_generation", quote=q)])
    v = out["domains"]["sequence_generation"]
    assert v["status"] == "SOURCE_QUOTE_LOCATED_REVIEW_REQUIRED"
    row = v["annotations"][0]
    assert TEXT[row["offset_start"]:row["offset_end"]] == q
    assert row["semantic_support_verified"] is False
    assert out["risk_of_bias_judgement"] == "NOT_ASSESSED"
    assert out["scientific_quality_assessed"] is False


def test_no_annotations_must_abstain():
    out = audit([])
    assert all(v["status"] == "UNKNOWN" for v in out["domains"].values())
    assert out["untraceable_domain_count"] == 0


def test_untraceable_quote_never_claims_supported():
    v = audit([annotate("sequence_generation", quote="We used a quantum unicorn randomizer.")])
    assert v["domains"]["sequence_generation"]["status"] == (
        "UNTRACEABLE_ANNOTATION_REVIEW_REQUIRED")
    assert v["source_located_domain_count"] == 0


def test_contradictory_annotations_flagged_not_auto_resolved():
    x = [annotate("sequence_generation", "reported_yes",
                  "Participants were randomly assigned using computer generated numbers."),
         annotate("sequence_generation", "reported_no",
                  "The primary endpoint was reported with a prespecified analysis plan.")]
    out = audit(x)
    assert out["contradictory_domain_count"] == 1
    assert out["domains"]["sequence_generation"]["status"].startswith("CONTRADICTORY")
    assert out["risk_of_bias_judgement"] == "NOT_ASSESSED"


def test_explicit_negative_is_not_assumed_inferred_from_keyword():
    q = "The report does not describe outcome blinding."
    out = audit([annotate("outcome_measurement", "reported_no", q)])
    assert out["domains"]["outcome_measurement"]["status"] == (
        "SOURCE_QUOTE_LOCATED_REVIEW_REQUIRED")
    assert out["domains"]["outcome_measurement"]["annotations"][0][
        "semantic_support_verified"] is False


def test_line_wrapped_whitespace_is_traceable():
    text = "Randomization was performed\n  by a central service."
    out = audit([annotate("sequence_generation", quote="performed by a central service")],
                text=text)
    assert out["source_located_domain_count"] == 1


def test_empty_short_quotes_never_count_as_verified():
    out = audit([annotate("sequence_generation", quote="assigned")])
    assert out["untraceable_domain_count"] == 1


def test_observational_specific_domains():
    out = audit([annotate("confounding", quote="We adjusted for age and sex using regression")],
                text="We adjusted for age and sex using regression",
                design="observational")
    assert "confounding" in out["domains"]
    assert "allocation_concealment" not in out["domains"]


@pytest.mark.parametrize("kwargs", [
    {"study_design": "unsupported"},
    {"outcome": ""},
    {"source_text": ""},
    {"study_id": ""},
])
def test_bad_audit_inputs(kwargs):
    defaults = {"study_id": "s", "outcome": "o", "study_design": "randomized_trial",
                "source_text": "some text", "annotations": []}
    defaults.update(kwargs)
    with pytest.raises(ValueError):
        audit_methodology_evidence(**defaults)


def test_wrong_domain_and_answer_fail_closed():
    with pytest.raises(ValueError):
        audit([annotate("unsupported", quote="some text")])
    with pytest.raises(ValueError):
        audit([annotate("sequence_generation", "green", "some text")])


def test_statistical_screen_detects_input_errors():
    out = audit_statistical_fields([
        {"sample_size": 12, "p_value": .03, "ci_lower": 1.0,
         "ci_upper": 2.0, "estimate": 1.5},
        {"sample_size": 0, "p_value": 1.2, "ci_lower": 3,
         "ci_upper": 1, "estimate": 4},
    ])
    assert out["records"][0]["flags"] == []
    assert "P_VALUE_OUT_OF_RANGE" in out["records"][1]["flags"]
    assert "REVERSED_CONFIDENCE_INTERVAL" in out["records"][1]["flags"]
    assert out["scientific_validity_assessed"] is False


@pytest.mark.parametrize("record", [{"p_value": float("nan")}, {"p_value": True},
                                    {"ci_lower": "x"}, {"estimate": float("inf")}])
def test_invalid_statistics_rejected(record):
    with pytest.raises(ValueError):
        audit_statistical_fields([record])


def test_missing_fields_are_not_assumed_invalid():
    result = audit_statistical_fields([{"study": "x"}])
    assert result["records"][0]["status"] == "NOT_ASSESSED"
    assert result["scientific_validity_assessed"] is False
