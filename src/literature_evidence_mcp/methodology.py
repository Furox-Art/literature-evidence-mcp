"""Auditable methodological reporting evidence; NOT a RoB2/GRADE judgement.

Domain labels are user-supplied annotations. Matching only establishes that the
quoted text occurs in the provided source, never that the label is scientifically true.
"""
from __future__ import annotations

import hashlib
import re
from typing import Any

RANDOMIZED_TRIAL = (
    "sequence_generation", "allocation_concealment", "baseline_imbalance",
    "deviations_from_intervention", "missing_outcome_data", "outcome_measurement",
    "selective_reporting",
)
OBSERVATIONAL = (
    "selection_of_participants", "confounding", "exposure_measurement",
    "missing_data", "outcome_measurement", "selective_reporting",
)
DOMAINS = {"randomized_trial": RANDOMIZED_TRIAL, "observational": OBSERVATIONAL}
ANSWERS = {"reported_yes", "reported_no", "unclear", "not_applicable"}


def _locate(text: str, quote: str) -> tuple[int, int] | None:
    # Flexible whitespace only. No fuzzy or semantic matches; punctuation stays literal.
    words = quote.split()
    if not words:
        return None
    pattern = r"\s+".join(re.escape(word) for word in words)
    # Avoid false positives such as "significant" inside "insignificant".
    # Preserve literal punctuation and flexible whitespace in quoted passages.
    if re.match(r"\w", words[0], flags=re.UNICODE):
        pattern = r"(?<!\w)" + pattern
    if re.search(r"\w$", words[-1], flags=re.UNICODE):
        pattern += r"(?!\w)"
    found = re.search(pattern, text, flags=re.IGNORECASE)
    return found.span() if found else None


def audit_methodology_evidence(
    study_id: str, outcome: str, study_design: str, source_text: str,
    annotations: list[dict[str, Any]],
) -> dict[str, Any]:
    """Validate cited reporting annotations, abstaining from risk-of-bias ratings.

    Any supplied reported_yes/reported_no assessment must cite a direct quote.
    This check NEVER semantically interprets a quotation. A human must determine
    whether the quotation supports the annotation and assess bias per outcome.
    """
    if not isinstance(study_id, str) or not 1 <= len(study_id.strip()) <= 300:
        raise ValueError("A study identifier is required (<=300 characters)")
    if not isinstance(outcome, str) or not 1 <= len(outcome.strip()) <= 500:
        raise ValueError("A result/outcome is required (<=500 characters)")
    if study_design not in DOMAINS:
        raise ValueError("Supported designs: randomized_trial or observational")
    if not isinstance(source_text, str) or not 1 <= len(source_text) <= 250_000:
        raise ValueError("Source text must contain 1-250000 characters")
    if not isinstance(annotations, list) or len(annotations) > 100:
        raise ValueError("Provide up to 100 reporting annotations")
    allowed = DOMAINS[study_design]
    grouped: dict[str, list] = {domain: [] for domain in allowed}
    for i, item in enumerate(annotations):
        if not isinstance(item, dict):
            raise TypeError(f"Annotation {i} must be an object")
        domain, answer = item.get("domain"), item.get("answer")
        if domain not in grouped or answer not in ANSWERS:
            raise ValueError(f"Invalid domain/answer in annotation {i}")
        quote = item.get("quote") or ""
        if not isinstance(quote, str) or len(quote) > 2500:
            raise ValueError(f"Quote in annotation {i} must be <=2500 characters")
        if answer in {"reported_yes", "reported_no"} and len(quote.strip()) < 12:
            # Retain untraceable quote as a finding, not a whole-tool failure.
            span = None
        else:
            span = _locate(source_text, quote) if quote.strip() else None
        if answer in {"unclear", "not_applicable"} and quote.strip():
            # Optional explanatory quote is allowed, but only reported as traced if found.
            pass
        grouped[domain].append({
            "annotation_number": i + 1,
            "answer": answer,
            "quote": quote,
            "source_match": span is not None,
            "offset_start": span[0] if span else None,
            "offset_end": span[1] if span else None,
            "semantic_support_verified": False,
        })
    domains = {}
    for domain, records in grouped.items():
        matched = [r for r in records if r["source_match"]]
        cited_answers = {r["answer"] for r in matched
                         if r["answer"] in {"reported_yes", "reported_no"}}
        if len(cited_answers) > 1:
            status = "CONTRADICTORY_ANNOTATIONS_REVIEW_REQUIRED"
        elif any(r["answer"] in {"reported_yes", "reported_no"}
                 and not r["source_match"] for r in records):
            status = "UNTRACEABLE_ANNOTATION_REVIEW_REQUIRED"
        elif cited_answers:
            status = "SOURCE_QUOTE_LOCATED_REVIEW_REQUIRED"
        elif records and all(r["answer"] == "not_applicable" for r in records):
            status = "NOT_APPLICABLE_USER_REPORTED"
        else:
            status = "UNKNOWN"
        domains[domain] = {"status": status, "annotations": records}
    statuses = [v["status"] for v in domains.values()]
    return {
        "study_id": study_id.strip(),
        "outcome": outcome.strip(),
        "study_design": study_design,
        "source_text_sha256": hashlib.sha256(source_text.encode("utf-8")).hexdigest(),
        "status": "EVIDENCE_TRACEABILITY_AUDIT_ONLY",
        "scientific_quality_assessed": False,
        "risk_of_bias_judgement": "NOT_ASSESSED",
        "domains": domains,
        "source_located_domain_count": statuses.count("SOURCE_QUOTE_LOCATED_REVIEW_REQUIRED"),
        "untraceable_domain_count": statuses.count("UNTRACEABLE_ANNOTATION_REVIEW_REQUIRED"),
        "contradictory_domain_count":
            statuses.count("CONTRADICTORY_ANNOTATIONS_REVIEW_REQUIRED"),
        "notice": (
            "Quote presence alone does not confirm meaning, randomization quality, "
            "absence of bias or methods performed. UNKNOWN is not evidence of omission. "
            "Human outcome-specific assessment and corroboration remain mandatory."
        ),
    }


def audit_statistical_fields(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Mechanical range/ordering checks on entered statistics; no inference."""
    if not isinstance(records, list) or not 1 <= len(records) <= 100:
        raise ValueError("Provide 1-100 statistical records")
    checked = []
    for i, record in enumerate(records):
        if not isinstance(record, dict):
            raise TypeError(f"Record {i} must be an object")
        flags: list[str] = []
        for key in ("p_value", "ci_lower", "ci_upper", "estimate"):
            value = record.get(key)
            if value is not None and (isinstance(value, bool) or
                                      not isinstance(value, (int, float)) or
                                      not float("-inf") < float(value) < float("inf")):
                raise ValueError(f"Invalid finite numeric {key} in record {i}")
        pval = record.get("p_value")
        if pval is not None and not 0 <= pval <= 1:
            flags.append("P_VALUE_OUT_OF_RANGE")
        n = record.get("sample_size")
        if n is not None and (isinstance(n, bool) or
                              not isinstance(n, int) or n < 1):
            flags.append("INVALID_SAMPLE_SIZE")
        lo, hi = record.get("ci_lower"), record.get("ci_upper")
        if (lo is None) != (hi is None):
            flags.append("PARTIAL_CONFIDENCE_INTERVAL")
        if lo is not None and hi is not None and lo > hi:
            flags.append("REVERSED_CONFIDENCE_INTERVAL")
        if (lo is not None and hi is not None and
                record.get("estimate") is not None and
                not lo <= record["estimate"] <= hi):
            flags.append("ESTIMATE_OUTSIDE_REPORTED_CI_REVIEW")
        evaluated = any(record.get(k) is not None for k in
                        ("sample_size", "p_value", "ci_lower", "ci_upper", "estimate"))
        checked.append({"index": i, "flags": flags, "status":
                        "REVIEW_REQUIRED" if flags else
                        "ARITHMETIC_SCREEN_PASSED" if evaluated else "NOT_ASSESSED"})
    return {"status": "NUMERICAL_CONSISTENCY_SCREEN_ONLY",
            "records": checked, "scientific_validity_assessed": False,
            "notice": "No effect estimation, raw data, hypothesis test or interval "
                      "construction has been independently reproduced."}
