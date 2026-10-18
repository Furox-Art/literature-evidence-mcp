import pytest

from literature_evidence_mcp import server
from literature_evidence_mcp.prisma_flow import PRISMA_ITEMS, review_flow


def fixture():
    numbers = {"databases": 2, "registers": 1, "other": 0, "duplicates_removed": 1}
    records = [
        {"record_id": "a", "reviewers": [
            {"reviewer_id": "a1", "decision": "include"},
            {"reviewer_id": "a2", "decision": "include"}]},
        {"record_id": "b", "reviewers": [
            {"reviewer_id": "b1", "decision": "exclude", "reason": "wrong population"},
            {"reviewer_id": "b2", "decision": "exclude", "reason": "wrong population"}]},
    ]
    checklist = dict.fromkeys(PRISMA_ITEMS, "reported")
    return numbers, records, checklist


def test_prisma_flow_consistent_but_not_certified():
    args = fixture()
    out = server.prisma_review_flow(*args)
    assert out["records_identified"] == 3
    assert out["records_screened"] == 2
    assert out["title_abstract_excluded"] == 1
    assert out["reports_sought_for_retrieval"] == 1
    assert out["reports_assessed_full_text"] is None
    assert out["status"] == "FLOW_INCOMPLETE_NEEDS_FULL_TEXT"
    assert out["prisma_2020_certified"] is False
    args[2]["2"] = "not_reported"
    assert review_flow(*args)["checklist_unreported_items"] == ["2"]


def test_empty_review_never_promises_certification():
    identified = {"databases": 0, "registers": 0, "other": 0,
                  "duplicates_removed": 0}
    out = review_flow(identified, [], dict.fromkeys(PRISMA_ITEMS, "not_applicable"))
    assert out["status"] == "EMPTY_REVIEW_REPORT_NOT_CERTIFIED"


def test_counts_checklist_validation():
    a, b, c = fixture()
    cases = [
        (None, b, c), ({}, b, c),
        ({**a, "databases": -1}, b, c),
        ({**a, "duplicates_removed": 99}, b, c),
        (a, [], c), (a, b, {}),
        (a, b, {**c, "2": "invalid"}),
    ]
    for case in cases:
        with pytest.raises(ValueError):
            review_flow(*case)
