"""Aggregate three actual same-query comparator executions without gold-score claims."""
from __future__ import annotations

import argparse
import hashlib
import json
from itertools import combinations
from pathlib import Path

EXPECTED_ENGINES = ("own", "athenaeum", "paper_search")
EXPECTED_PROVIDERS = ("openalex", "crossref", "europepmc")
EXPECTED_QUERIES = (
    "cortical predictive processing",
    "randomized controlled trial childhood anxiety",
    "quantum entanglement bell inequalities",
)


def aggregate(executions: dict[str, dict], revisions: dict[str, str]) -> dict:
    if set(executions) != set(EXPECTED_ENGINES) or set(revisions) != set(EXPECTED_ENGINES):
        raise ValueError("Require every pinned competitor and all revisions")
    if any(not isinstance(v, str) or len(v) != 40
           or any(ch not in "0123456789abcdef" for ch in v)
           for v in revisions.values()):
        raise ValueError("Expected exact Git SHA for each engine")
    table = {}
    doi_by_engine = {}
    warnings = []
    for name in EXPECTED_ENGINES:
        item = executions[name]
        if not isinstance(item, dict) or item.get("engine") != name:
            raise ValueError("Engine identification mismatch")
        if tuple(item.get("providers") or ()) != EXPECTED_PROVIDERS:
            raise ValueError("Provider list or order changed")
        if item.get("per_provider_limit") != 5:
            raise ValueError("Provider budget mismatch")
        rows = item.get("results")
        if not isinstance(rows, list) or len(rows) != len(EXPECTED_QUERIES):
            raise ValueError("Missing or surplus shared queries")
        counts = {"queries": 0, "total_records": 0, "total_dois": 0,
                  "status_counts": {}, "seconds_sum_observed": 0.0}
        per_query = {}
        doi_by_engine[name] = {}
        for q, expected in zip(rows, EXPECTED_QUERIES):
            if not isinstance(q, dict) or q.get("query") != expected:
                raise ValueError("Query alignment mismatch")
            status = q.get("status")
            if status not in ("OK", "PARTIAL", "ERROR", "BLOCKED"):
                raise ValueError("Unrecognized execution status")
            records, doi_count = q.get("deduped_record_count"), q.get("doi_count")
            ids, seconds = q.get("dois"), q.get("seconds")
            if (not isinstance(records, int) or isinstance(records, bool)
                or not 0 <= records <= 45 or not isinstance(doi_count, int)
                or isinstance(doi_count, bool) or not 0 <= doi_count <= records
                or not isinstance(ids, list) or len(ids) != doi_count
                or not all(isinstance(d, str) and d.strip() for d in ids)
                or len(set(ids)) != len(ids)
                or not isinstance(seconds, (float, int)) or seconds < 0):
                raise ValueError("Unusable DOI result counts or duration")
            if status in ("ERROR", "BLOCKED") and (records or doi_count):
                raise ValueError("Failed search cannot return a success count")
            errors = q.get("errors", {})
            if not isinstance(errors, dict):
                raise TypeError("Unexpected provider error details")
            counts["queries"] += 1
            counts["total_records"] += records
            counts["total_dois"] += doi_count
            counts["seconds_sum_observed"] += float(seconds)
            counts["status_counts"][status] = counts["status_counts"].get(status, 0) + 1
            doi_by_engine[name][expected] = set(ids)
            per_query[expected] = {
                "status": status,
                "records": records,
                "doi_count": doi_count,
                "seconds_observed": seconds,
                "provider_errors_present": bool(errors),
            }
        table[name] = {"summary": counts, "per_query": per_query}
        if name == "athenaeum":
            warnings.append("Athenaeum meta-search may suppress per-provider failures; errors cannot be audited equivalently.")
    pairwise = {}
    for a, b in combinations(EXPECTED_ENGINES, 2):
        matches = {}
        for q in EXPECTED_QUERIES:
            aa, bb = doi_by_engine[a][q], doi_by_engine[b][q]
            union = aa | bb
            matches[q] = {
                "doi_overlap_count": len(aa & bb),
                "doi_union_count": len(union),
                "doi_jaccard": len(aa & bb) / len(union) if union else None,
            }
        pairwise[f"{a}__{b}"] = matches
    return {
        "status": "LIVE_SAME_QUERY_DESCRIPTIVE_SMOKE_NOT_GOLD_BENCHMARK",
        "query_set": list(EXPECTED_QUERIES),
        "shared_provider_set": list(EXPECTED_PROVIDERS),
        "max_results_per_provider": 5,
        "revisions": revisions,
        "results": table,
        "doi_overlap_not_relevance": pairwise,
        "limitations": [
            "No independent per-query article relevance labels or publication-level ground truth.",
            "Record counts, DOI agreement, and observed latency are NOT search precision/recall.",
            "Provider caching, quota and errors can differ between engines.",
            "Athenaeum can suppress upstream provider errors even if top-level status is OK.",
            "These three fixed historical queries are convenience smokes, not a blinded sample.",
            "No conclusion about clinical validity, evidence classification, or systematic review completeness.",
        ] + warnings,
        "independent_blind_validation_completed": False,
        "scientific_competitor_superiority_demonstrated": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    for engine in EXPECTED_ENGINES:
        parser.add_argument(f"--{engine.replace('_', '-')}", type=Path, required=True)
    parser.add_argument("--revisions", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    files = {
        engine: getattr(args, engine) for engine in EXPECTED_ENGINES
    }
    source = {engine: json.loads(path.read_text()) for engine, path in files.items()}
    revisions = json.loads(args.revisions.read_text())
    result = aggregate(source, revisions)
    result["execution_artifact_sha256"] = {
        engine: hashlib.sha256(path.read_bytes()).hexdigest() for engine, path in files.items()
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n")
    print("DESCRIPTIVE_LIVE_3_ENGINE_COMPARISON_ONLY")


if __name__ == "__main__":
    main()
