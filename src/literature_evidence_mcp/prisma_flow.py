"""PRISMA 2020 flow preparation, not certification of a systematic review."""
from __future__ import annotations

# Official PRISMA 2020: 27 numbered items, 42 reporting rows.
# Sub-items: 10a-b, 13a-f, 16a-b, 20a-d, 23a-d, 24a-c.
SUBITEMS = {10: "ab", 13: "abcdef", 16: "ab", 20: "abcd",
            23: "abcd", 24: "abc"}
PRISMA_ITEMS = tuple(f"{i}{letter}" for i in range(1, 28)
                     for letter in (SUBITEMS.get(i, ("",))))



def review_flow(identified: dict, records: list[dict], checklist: dict) -> dict:
    """Count auditable report/study flow with missing stages explicitly UNKNOWN."""
    if not isinstance(identified, dict) or set(identified) != {
        "databases", "registers", "other", "duplicates_removed",
    }:
        raise ValueError("identification counts must be complete")
    if any(type(x) is not int or x < 0 for x in identified.values()):
        raise ValueError("identification counts must be nonnegative integers")
    total = sum(identified[k] for k in ("databases", "registers", "other"))
    screened = total - identified["duplicates_removed"]
    if screened < 0 or not isinstance(records, list) or len(records) != screened:
        raise ValueError("screened record count inconsistent with identification")
    if not isinstance(checklist, dict) or set(checklist) != set(PRISMA_ITEMS):
        raise ValueError("PRISMA checklist requires every named reporting item")
    if any(x not in {"reported", "not_reported", "not_applicable"} for x in checklist.values()):
        raise ValueError("invalid PRISMA checklist status")
    from literature_evidence_mcp.prisma import dual_screen
    summary = dual_screen(records)
    report = {**identified, "records_identified": total, "records_screened": screened,
              "title_abstract_excluded": summary["excluded_records"],
              "reports_sought_for_retrieval": summary["included_records"],
              "reviewer_conflicts_unresolved": summary["unresolved_conflicts"],
              "exclusion_reasons": summary["exclusion_reasons"],
              "reports_not_retrieved": None, "reports_assessed_full_text": None,
              "studies_included": None, "checklist": checklist,
              "checklist_unreported_items": [key for key, value in checklist.items()
                                              if value == "not_reported"]}
    status = "FLOW_INCOMPLETE_NEEDS_FULL_TEXT" if screened or report["checklist_unreported_items"] else "EMPTY_REVIEW_REPORT_NOT_CERTIFIED"
    report["status"] = status
    report["prisma_2020_certified"] = False
    return report
