"""Source-bound methodology audit for Europe PMC primary full-text XML.

All labels remain human annotations. One network retrieval provides the source
content, and every located quote must be entirely inside one JATS paragraph.
"""
from __future__ import annotations

import hashlib
from typing import Any

from literature_evidence_mcp.methodology import (
    _locate,
    audit_methodology_evidence,
)


def audit_pmc_paragraph_evidence(
    fulltext: dict[str, Any],
    outcome: str,
    study_design: str,
    annotations: list[dict[str, Any]],
) -> dict[str, Any]:
    """Use already-fetched Europe PMC JATS paragraph spans as source anchors.

    Direct text presence only; cannot verify original PDF pagination, semantics,
    research claims, randomization quality or risk-of-bias categories.
    """
    pmcid = fulltext.get("pmcid")
    if not isinstance(pmcid, str) or not pmcid.startswith("PMC"):
        raise ValueError("Expected directly retrieved Europe PMC record")
    source_sha = fulltext.get("sha256_xml")
    if not isinstance(source_sha, str) or len(source_sha) != 64:
        raise ValueError("Missing direct XML provenance")
    spans = fulltext.get("spans")
    if not isinstance(spans, list):
        raise TypeError("Expected direct JATS paragraph spans")
    for item in spans:
        if not isinstance(item, dict) or not isinstance(item.get("text"), str):
            raise TypeError("Invalid paragraph record")
        expected = hashlib.sha256(item["text"].encode("utf-8")).hexdigest()
        if item.get("sha256_text") != expected:
            raise ValueError("Paragraph content/hash mismatch")
    source_text = "\n\n".join(item["text"] for item in spans)
    if not source_text:
        raise ValueError("No extractable article body paragraphs")
    if len(source_text) > 250_000:
        raise ValueError("Fetched article source exceeds audit limit")
    audit = audit_methodology_evidence(
        pmcid, outcome, study_design, source_text, annotations,
    )
    truncated = bool(fulltext.get("truncated"))
    matched_domains = 0
    unverified_domains = 0
    for domain in audit["domains"].values():
        rows = domain["annotations"]
        yesno = []
        for row in rows:
            # Source is direct-paragraph constrained. A cross-paragraph or
            # section-title match does not count.
            quote = row["quote"]
            found = []
            if quote.strip() and (row["answer"] not in {"reported_yes", "reported_no"}
                                  or len(quote.strip()) >= 12):
                for item in spans:
                    loc = _locate(item["text"], quote)
                    if loc is not None:
                        found.append({
                            "span_id": item["span_id"],
                            "section": item["section"],
                            "paragraph_index": item["paragraph_index"],
                            "sha256_text": item["sha256_text"],
                            "offset_start": loc[0],
                            "offset_end": loc[1],
                        })
            row["source_match"] = bool(found)
            row["matched_paragraphs"] = found
            row["offset_start"] = None
            row["offset_end"] = None
            row["semantic_support_verified"] = False
            if row["answer"] in {"reported_yes", "reported_no"}:
                yesno.append(row)
        found_types = {r["answer"] for r in yesno if r["source_match"]}
        if len(found_types) > 1:
            status = "CONTRADICTORY_ANNOTATIONS_REVIEW_REQUIRED"
        elif any(not r["source_match"] for r in yesno):
            status = ("NOT_VERIFIED_SOURCE_TRUNCATED" if truncated
                      else "UNTRACEABLE_ANNOTATION_REVIEW_REQUIRED")
        elif found_types:
            status = "SOURCE_QUOTE_LOCATED_REVIEW_REQUIRED"
        elif rows and all(r["answer"] == "not_applicable" for r in rows):
            status = "NOT_APPLICABLE_USER_REPORTED"
        else:
            status = "UNKNOWN"
        domain["status"] = status
        if status == "SOURCE_QUOTE_LOCATED_REVIEW_REQUIRED":
            matched_domains += 1
        elif status in {"NOT_VERIFIED_SOURCE_TRUNCATED",
                        "UNTRACEABLE_ANNOTATION_REVIEW_REQUIRED"}:
            unverified_domains += 1
    audit["source_located_domain_count"] = matched_domains
    audit["untraceable_domain_count"] = unverified_domains
    audit["contradictory_domain_count"] = sum(
        v["status"] == "CONTRADICTORY_ANNOTATIONS_REVIEW_REQUIRED"
        for v in audit["domains"].values()
    )
    audit["xml_sha256"] = source_sha
    audit["pmcid"] = pmcid
    audit["fulltext_origin"] = "EUROPE_PMC_PMC_XML"
    audit["retrieval_truncated"] = truncated
    audit["paragraph_count_read"] = len(spans)
    audit["status"] = "SOURCE_BOUND_EVIDENCE_AUDIT_ONLY"
    audit["notice"] = (
        "Retrieved JATS paragraphs independently, compared direct literal quotes; "
        "none of the labels or method quality were independently assessed. "
        "Truncated source prevents interpreting missing quotes as absent."
    )
    return audit
