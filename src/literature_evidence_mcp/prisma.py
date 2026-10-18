"""Two-reviewer screening and explicit one-stage PRISMA-compatible counts."""
from __future__ import annotations


def dual_screen(records: list[dict]) -> dict:
    if not isinstance(records, list) or len(records) > 100000:
        raise ValueError("Expected at most 100000 records")
    seen = set()
    included = excluded = pending = 0
    reasons: dict[str, int] = {}
    conflicts = []
    for row in records:
        if not isinstance(row, dict):
            raise TypeError("Each record must be an object")
        rid = row.get("record_id")
        if not isinstance(rid, str) or not rid.strip() or rid in seen:
            raise ValueError("record_id must be unique and nonempty")
        seen.add(rid)
        reviewers = row.get("reviewers")
        if not isinstance(reviewers, list) or len(reviewers) != 2:
            raise ValueError("Exactly two reviewer decisions required")
        identities = [r.get("reviewer_id") if isinstance(r, dict) else None for r in reviewers]
        if any(not isinstance(r, str) or not r.strip() for r in identities) or identities[0] == identities[1]:
            raise ValueError("Reviewers must be distinct and identified")
        decisions = [r.get("decision") for r in reviewers]
        if any(d not in {"include", "exclude"} for d in decisions):
            raise ValueError("Invalid decision")
        if any(r["decision"] == "exclude" and not str(r.get("reason", "")).strip() for r in reviewers):
            raise ValueError("Exclusion reason required")
        if decisions[0] != decisions[1]:
            pending += 1
            conflicts.append(rid)
        elif decisions[0] == "include":
            included += 1
        else:
            excluded += 1
            reason = str(reviewers[0]["reason"]).strip()
            reasons[reason] = reasons.get(reason, 0) + 1
    return {"status": "ONE_STAGE_TWO_REVIEWER_ACCOUNTING",
            "records_screened": len(records), "included_records": included,
            "excluded_records": excluded, "unresolved_conflicts": pending,
            "conflicting_ids": conflicts, "exclusion_reasons": reasons,
            "full_prisma_2020_report_complete": False, "reports_retrieved": None,
            "studies_included": None,
            "notice": "One-stage screening only, not a complete 27-item PRISMA report or full study-level flow."}
