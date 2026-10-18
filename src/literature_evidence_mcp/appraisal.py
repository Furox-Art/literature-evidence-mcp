"""Outcome-specific human appraisal records. Not Cochrane's proprietary decision algorithms."""
from __future__ import annotations

DOMAINS = {
    "ROB2": ("randomization_process", "deviations", "missing_data", "outcome_measurement", "selective_reporting"),
    # ROBINS-I V2 draft (20 November 2025) has SIX domains, unlike v1 (2016).
    "ROBINS_I_V2": ("confounding", "intervention_classification", "participant_selection",
                    "missing_data", "outcome_measurement", "selective_reporting"),
}
RATINGS = {"ROB2": {"low", "some_concerns", "high"},
           "ROBINS_I_V2": {"low", "moderate", "serious", "critical", "no_information"}}
DOWN = ("risk_of_bias", "inconsistency", "indirectness", "imprecision", "publication_bias")
UP = ("large_effect", "dose_response", "opposing_residual_confounding")


def risk_of_bias_review(framework: str, study_id: str, outcome: str, reviewers: list[dict],
                        effect_of_interest: str = "") -> dict:
    if framework not in DOMAINS:
        raise ValueError("Unsupported framework")
    if not isinstance(study_id, str) or not study_id.strip() or not isinstance(outcome, str) or not outcome.strip():
        raise ValueError("Study ID and outcome required")
    if framework == "ROBINS_I_V2" and effect_of_interest not in {"assignment", "per_protocol"}:
        raise ValueError("ROBINS-I V2 effect_of_interest must be assignment or per_protocol")
    if not isinstance(reviewers, list) or len(reviewers) != 2:
        raise ValueError("Two reviewer records required")
    ids = []
    for reviewer in reviewers:
        if not isinstance(reviewer, dict):
            raise TypeError("Reviewer must be an object")
        rid, marks = reviewer.get("reviewer_id"), reviewer.get("domains")
        if not isinstance(rid, str) or not rid.strip() or not isinstance(marks, dict) or set(marks) != set(DOMAINS[framework]):
            raise ValueError("Reviewer identity and every domain are mandatory")
        ids.append(rid)
        for domain in DOMAINS[framework]:
            mark = marks[domain]
            if not isinstance(mark, dict) or mark.get("judgment") not in RATINGS[framework]:
                raise ValueError(f"Invalid domain judgment: {domain}")
            if not isinstance(mark.get("rationale"), str) or len(mark["rationale"].strip()) < 12:
                raise ValueError(f"Human rationale required: {domain}")
            if not isinstance(mark.get("source_id"), str) or not mark["source_id"].strip():
                raise ValueError(f"Source attribution required: {domain}")
    if ids[0] == ids[1]:
        raise ValueError("Independent reviewer identities required")
    disagreements = [domain for domain in DOMAINS[framework]
                     if reviewers[0]["domains"][domain]["judgment"] != reviewers[1]["domains"][domain]["judgment"]]
    return {
        "status": "NEEDS_ADJUDICATION" if disagreements else "TWO_REVIEWERS_AGREE_NOT_CERTIFIED",
        "framework": framework, "study_id": study_id, "outcome": outcome,
        "framework_revision": "ROBINS-I_V2_2025-11_DRAFT" if framework == "ROBINS_I_V2"
                              else "ROB2",
        "effect_of_interest": effect_of_interest or None,
        "disagreement_domains": disagreements,
        "agreed_domain_judgments": {d: reviewers[0]["domains"][d]["judgment"]
                                   for d in DOMAINS[framework] if d not in disagreements},
        "automated_bias_judgment": False,
        "notice": "Human domain inputs only. Official signaling-question algorithms not implemented; semantics are not independently verified.",
    }


def grade_domain_record(outcome: str, design: str, down: dict, up: dict, reviewer_id: str, rationale: str) -> dict:
    if not isinstance(outcome, str) or not outcome.strip() or design not in {"randomized", "non_randomized"}:
        raise ValueError("Outcome/design required")
    if not isinstance(reviewer_id, str) or not reviewer_id.strip() or not isinstance(rationale, str) or len(rationale.strip()) < 12:
        raise ValueError("Human reviewer and evidence rationale required")
    if not isinstance(down, dict) or set(down) != set(DOWN) or not isinstance(up, dict) or set(up) != set(UP):
        raise ValueError("All GRADE domains must be entered")
    if any(type(value) is not int or value not in (0, 1, 2) for value in down.values()):
        raise ValueError("Invalid downgrade")
    if any(type(value) is not int or value not in (0, 1) for value in up.values()):
        raise ValueError("Invalid upgrade")
    return {
        "status": "HUMAN_GRADE_INPUT_NOT_CERTIFIED", "outcome": outcome, "design": design,
        "downgrade_total": sum(down.values()), "upgrade_total": sum(up.values()),
        "reviewer_id": reviewer_id, "rationale": rationale,
        "automatic_certainty_category": None,
        "notice": "No arithmetic-only GRADE category. Thresholds, bias and study-level evidence require expert review.",
    }
