"""Manual framework logic: all domain decisions must come from identifiable humans."""
import pytest

from literature_evidence_mcp import server
from literature_evidence_mcp.appraisal import (
    DOMAINS,
    DOWN,
    UP,
    grade_domain_record,
    risk_of_bias_review,
)
from literature_evidence_mcp.graph_audit import publication_alerts
from literature_evidence_mcp.prisma import dual_screen


def humans(framework):
    return [{"reviewer_id": name, "domains": {d: {
        "judgment": "low", "rationale": "Assessed against supplied source.",
        "source_id": "paper:123"} for d in DOMAINS[framework]}}
        for name in ("assessor1", "assessor2")]


@pytest.mark.parametrize("framework", ["ROB2", "ROBINS_I_V2"])
def test_complete_human_risk_assessment(framework):
    mode = "assignment" if framework == "ROBINS_I_V2" else ""
    result = server.record_risk_of_bias(framework, "S1", "survival", humans(framework), mode)
    assert result["status"] == "TWO_REVIEWERS_AGREE_NOT_CERTIFIED"
    assert len(result["agreed_domain_judgments"]) == len(DOMAINS[framework])
    assert result["automated_bias_judgment"] is False
    reviewers = humans(framework)
    reviewers[1]["domains"][DOMAINS[framework][0]]["judgment"] = (
        "high" if framework == "ROB2" else "serious")
    out = risk_of_bias_review(framework, "S1", "survival", reviewers, mode)
    assert out["status"] == "NEEDS_ADJUDICATION"
    assert len(out["disagreement_domains"]) == 1


@pytest.mark.parametrize("framework,study,outcome,reviewers,error", [
    ("wrong", "S1", "outcome", [], ValueError),
    ("ROB2", "", "outcome", [], ValueError),
    ("ROB2", "S1", "", [], ValueError),
    ("ROB2", "S1", "outcome", [], ValueError),
    ("ROB2", "S1", "outcome", [None, {}], TypeError),
])
def test_appraisal_rejects_missing(framework, study, outcome, reviewers, error):
    with pytest.raises(error):
        risk_of_bias_review(framework, study, outcome, reviewers)


def test_appraisal_rejects_unindependent_and_unsubstantiated():
    a = humans("ROB2")
    a[1]["reviewer_id"] = "assessor1"
    with pytest.raises(ValueError, match="Independent"):
        risk_of_bias_review("ROB2", "S1", "outcome", a)
    a = humans("ROB2")
    a[0]["domains"]["missing_data"]["judgment"] = "invented"
    with pytest.raises(ValueError, match="Invalid"):
        risk_of_bias_review("ROB2", "S1", "outcome", a)
    a = humans("ROB2")
    a[0]["domains"]["missing_data"]["rationale"] = "bad"
    with pytest.raises(ValueError, match="rationale"):
        risk_of_bias_review("ROB2", "S1", "outcome", a)
    a = humans("ROB2")
    a[0]["domains"]["missing_data"]["source_id"] = ""
    with pytest.raises(ValueError, match="Source"):
        risk_of_bias_review("ROB2", "S1", "outcome", a)
    a = humans("ROB2")
    del a[0]["domains"]["missing_data"]
    with pytest.raises(ValueError, match="domain"):
        risk_of_bias_review("ROB2", "S1", "outcome", a)


def test_grade_record_not_automatic_final_certainty():
    down = dict.fromkeys(DOWN, 0)
    up = dict.fromkeys(UP, 0)
    result = server.record_grade("quality of life", "randomized", down, up,
                                 "reviewer 1", "Human evaluation pending.")
    assert result["automatic_certainty_category"] is None
    assert result["status"] == "HUMAN_GRADE_INPUT_NOT_CERTIFIED"
    down["risk_of_bias"] = 2
    up["large_effect"] = 1
    result = grade_domain_record("life", "non_randomized", down, up,
                                 "reviewer 1", "Detailed study-level reasoning.")
    assert result["downgrade_total"] == 2
    assert result["upgrade_total"] == 1


def test_grade_rejects_unsubstantiated_inputs():
    down = dict.fromkeys(DOWN, 0)
    up = dict.fromkeys(UP, 0)
    variants = [
        ("", "randomized", down, up, "A", "Detailed study-level reasoning."),
        ("life", "wrong", down, up, "A", "Detailed study-level reasoning."),
        ("life", "randomized", down, up, "", "Detailed study-level reasoning."),
        ("life", "randomized", down, up, "A", "bad"),
        ("life", "randomized", {}, up, "A", "Detailed study-level reasoning."),
        ("life", "randomized", down, {}, "A", "Detailed study-level reasoning."),
        ("life", "randomized", {**down, "risk_of_bias": 3}, up, "A", "Detailed study-level reasoning."),
        ("life", "randomized", down, {**up, "large_effect": True}, "A", "Detailed study-level reasoning."),
    ]
    for args in variants:
        with pytest.raises(ValueError):
            grade_domain_record(*args)


def records():
    return [
        {"record_id": "A", "reviewers": [{"reviewer_id": "R1", "decision": "include"},
                                         {"reviewer_id": "R2", "decision": "include"}]},
        {"record_id": "B", "reviewers": [{"reviewer_id": "R1", "decision": "exclude", "reason": "design"},
                                         {"reviewer_id": "R2", "decision": "exclude", "reason": "design"}]},
        {"record_id": "C", "reviewers": [{"reviewer_id": "R1", "decision": "include"},
                                         {"reviewer_id": "R2", "decision": "exclude", "reason": "population"}]},
    ]


def test_dual_prisma_accounting_with_explicit_conflicts():
    out = server.prisma_dual_screen(records())
    assert (out["included_records"], out["excluded_records"], out["unresolved_conflicts"]) == (1, 1, 1)
    assert out["conflicting_ids"] == ["C"]
    assert out["exclusion_reasons"] == {"design": 1}
    assert out["full_prisma_2020_report_complete"] is False
    assert dual_screen([])["records_screened"] == 0


def test_prisma_validations():
    bad = [
        None, [None], [{"record_id": "", "reviewers": []}],
        [records()[0], records()[0]],
        [{"record_id": "x", "reviewers": []}],
        [{"record_id": "x", "reviewers": [{"reviewer_id": "same"}, {"reviewer_id": "same"}]}],
        [{"record_id": "x", "reviewers": [{"reviewer_id": "A", "decision": "undecided"},
                                          {"reviewer_id": "B", "decision": "include"}]}],
        [{"record_id": "x", "reviewers": [{"reviewer_id": "A", "decision": "exclude"},
                                          {"reviewer_id": "B", "decision": "include"}]}],
    ]
    for value in bad:
        with pytest.raises((ValueError, TypeError)):
            dual_screen(value)


def test_notices_traverse_only_source_linked_citation_edges():
    nodes = [{"id": x} for x in ["A", "B", "C", "D"]]
    edges = [{"cited_id": "A", "citing_id": "B", "source_id": "crossref:edge1"},
             {"cited_id": "B", "citing_id": "C", "source_id": "crossref:edge2"},
             {"cited_id": "C", "citing_id": "A", "source_id": "crossref:loop"}]
    out = server.propagation_alerts(nodes, edges, [
        {"paper_id": "A", "kind": "retraction", "source_id": "publisher:not1"}])
    assert [a["paper_id"] for a in out["alerts"]] == ["A", "B", "C"]
    assert out["alerts"][0]["status"] == "DIRECT_NOTICE"
    assert out["alerts"][2]["status"] == "CITING_PAPER_REVIEW_ALERT_ONLY"
    assert out["alerts"][2]["citation_evidence_chain"] == ["crossref:edge1", "crossref:edge2"]


def test_graph_validation_strict():
    n = [{"id": "A"}]
    samples = [
        (None, [], []), ([{}], [], []), (n + n, [], []),
        (n, [None], []), (n, [{"cited_id": "A", "citing_id": "B"}], []),
        (n, [], [None]), (n, [], [{"paper_id": "A", "kind": "fake", "source_id": "a"}]),
        (n, [], [{"paper_id": "A", "kind": "correction", "source_id": ""}]),
    ]
    for args in samples:
        with pytest.raises((ValueError, TypeError)):
            publication_alerts(*args)


def test_propagation_graph_size_bound():
    with pytest.raises(ValueError, match="Graph too large"):
        publication_alerts([{"id": str(i)} for i in range(10001)], [], [])



def test_robins_v2_nov2025_six_domains_and_effect():
    assert DOMAINS["ROBINS_I_V2"] == (
        "confounding", "intervention_classification", "participant_selection",
        "missing_data", "outcome_measurement", "selective_reporting",
    )
    reviewers = humans("ROBINS_I_V2")
    with pytest.raises(ValueError, match="effect_of_interest"):
        server.record_risk_of_bias("ROBINS_I_V2", "study", "outcome", reviewers)
    out = server.record_risk_of_bias(
        "ROBINS_I_V2", "study", "outcome", reviewers, "per_protocol")
    assert out["effect_of_interest"] == "per_protocol"
    assert out["framework_revision"] == "ROBINS-I_V2_2025-11_DRAFT"
    reviewers[0]["domains"]["confounding"]["judgment"] = "no_information"
    out = server.record_risk_of_bias(
        "ROBINS_I_V2", "study", "outcome", reviewers, "assignment")
    assert out["status"] == "NEEDS_ADJUDICATION"
