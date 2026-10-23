"""Two independent, offline comparator tracks; never assert a scientific winner.

Inputs are externally supplied frozen gold and per-system predictions. This
function tests alignment and reports diagnostics, not blindness/provenance
authenticity. Gold relevance may contain only known positives.
"""
from __future__ import annotations

from itertools import combinations

LABELS = ("SUPPORT", "REFUTE", "INSUFFICIENT")
NON_DECISIONS = ("ABSTAIN", "NULL", "MIXED", "BLOCKED", "ERROR")
RETRIEVAL_STATES = ("OK", "PARTIAL", "NULL", "BLOCKED", "ERROR")
CUTS = (1, 5, 10)


def _rows(items: object, name: str) -> dict[str, dict]:
    if not isinstance(items, list) or not items:
        raise ValueError(f"{name} requires nonempty rows")
    result = {}
    for item in items:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            raise TypeError(f"{name} row needs string id")
        ident = item["id"]
        if not ident.strip() or len(ident) > 250 or ident in result:
            raise ValueError(f"{name} blank, overlong, or duplicate id")
        result[ident] = item
    return result


def _strings(value: object, field: str) -> list[str]:
    if not isinstance(value, list) or any(
        not isinstance(v, str) or not v.strip() or len(v) > 250 for v in value
    ):
        raise ValueError(f"{field} must be a list of short nonempty strings")
    if len(value) != len(set(value)):
        raise ValueError(f"{field} must not contain duplicate ids")
    return value


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _retrieval(gold: dict[str, dict], rows: dict[str, dict]) -> dict:
    scores: dict[int, list[float]] = {cut: [] for cut in CUTS}
    reciprocal = []
    without_positive = 0
    state_counts = {state: 0 for state in RETRIEVAL_STATES}
    for ident, ref in gold.items():
        relevant = set(_strings(ref.get("known_positive_ids"), "known_positive_ids"))
        row = rows[ident]
        state = row.get("status")
        if state not in RETRIEVAL_STATES:
            raise ValueError("retrieval status not recognized")
        ranked = _strings(row.get("ranked_ids"), "ranked_ids")
        if state in {"NULL", "BLOCKED", "ERROR"} and ranked:
            raise ValueError("failed retrieval must not supply ranked results")
        state_counts[state] += 1
        if not relevant:
            without_positive += 1
            continue
        position = {paper: i for i, paper in enumerate(ranked)}
        for cut in CUTS:
            scores[cut].append(sum(
                position.get(paper, len(ranked) + cut) < cut for paper in relevant
            ) / len(relevant))
        found = [position[paper] for paper in relevant if paper in position]
        reciprocal.append(1 / (min(found) + 1) if found else 0.0)
    return {
        "queries_total": len(gold), "queries_without_known_positive": without_positive,
        "queries_scored": len(reciprocal),
        "state_counts": state_counts,
        "known_positive_recall_at_k": {
            str(k): _mean(scores[k]) for k in CUTS
        },
        "mrr_first_known_positive": _mean(reciprocal),
        "precision_at_k": None, "false_positive_rate": None,
        "precision_reason": "INCOMPLETE_CORPUS_RELEVANCE_JUDGMENTS",
    }


def _classification(gold: dict[str, dict], rows: dict[str, dict]) -> dict:
    matrix = {label: {pred: 0 for pred in (*LABELS, *NON_DECISIONS)}
              for label in LABELS}
    for ident, record in gold.items():
        truth = record.get("label")
        pred = rows[ident].get("prediction")
        if truth not in LABELS or pred not in (*LABELS, *NON_DECISIONS):
            raise ValueError("Unsupported gold or predicted evidence label")
        matrix[truth][pred] += 1
    decided = sum(matrix[t][p] for t in LABELS for p in LABELS)
    correct = sum(matrix[t][t] for t in LABELS)
    n = len(gold)
    f1 = {}
    recall = {}
    for label in LABELS:
        tp = matrix[label][label]
        actual = sum(matrix[label].values())
        predicted = sum(matrix[truth][label] for truth in LABELS)
        recall[label] = tp / actual if actual else None
        denominator = actual + predicted
        f1[label] = 2 * tp / denominator if denominator else None
    return {
        "cases_total": n, "decided": decided, "non_decisions": n - decided,
        "decision_coverage": decided / n,
        "accuracy_all_cases": correct / n,
        "selective_accuracy": correct / decided if decided else None,
        "macro_f1": _mean([x for x in f1.values() if x is not None]),
        "per_class_recall": recall, "per_class_f1": f1,
        "confusion": matrix, "gold_labels": list(LABELS),
        "non_decisions_are_not_neutral": True,
    }


def audit_dual_track(gold: dict, systems: dict) -> dict:
    """Score matched externally supplied outputs; no unapproved primary endpoint."""
    if not isinstance(gold, dict) or not isinstance(systems, dict):
        raise TypeError("gold and systems must be objects")
    if set(gold) != {"retrieval", "classification"} or len(systems) < 2:
        raise ValueError("Both gold tracks and at least two systems are required")
    reference = {track: _rows(gold[track], f"gold.{track}") for track in gold}
    if any(not isinstance(system, str) or not system.strip() or len(system) > 80
           for system in systems):
        raise ValueError("System identifiers must be nonempty bounded strings")
    results: dict[str, dict[str, dict]] = {"retrieval": {}, "classification": {}}
    for name, payload in systems.items():
        if not isinstance(payload, dict) or set(payload) != set(reference):
            raise ValueError("Both system tracks are required")
        for track, baseline in reference.items():
            rows = _rows(payload[track], f"{name}.{track}")
            if set(rows) != set(baseline):
                raise ValueError("Gold and system case IDs must match exactly")
            results[track][name] = (
                _retrieval(baseline, rows) if track == "retrieval"
                else _classification(baseline, rows)
            )
    paired: dict[str, dict[str, dict]] = {"retrieval": {}, "classification": {}}
    for first, second in combinations(sorted(systems), 2):
        key = f"{first}__versus__{second}"
        for cut in CUTS:
            a = results["retrieval"][first]["known_positive_recall_at_k"][str(cut)]
            b = results["retrieval"][second]["known_positive_recall_at_k"][str(cut)]
            paired["retrieval"].setdefault(key, {})[f"known_positive_recall_at_{cut}_delta"] = (
                a - b if a is not None and b is not None else None
            )
        for metric in ("accuracy_all_cases", "macro_f1", "decision_coverage"):
            paired["classification"].setdefault(key, {})[f"{metric}_delta"] = (
                results["classification"][first][metric] -
                results["classification"][second][metric]
            )
    return {
        "status": "DESCRIPTIVE_TWO_TRACK_COMPARISON_NO_SCIENTIFIC_WINNER",
        "retrieval": results["retrieval"], "classification": results["classification"],
        "paired_descriptive_deltas": paired,
        "independent_gold_provenance_verified": False,
        "blinded_evaluation_verified": False,
        "competitor_executions_verified": False,
        "clinical_validity_verified": False,
        "primary_metric_selected": False,
        "significance_test_performed": False,
        "limitations": [
            "Gold independence, blinding and competitor executions need separate audit.",
            "No shared composite score or unapproved primary endpoint.",
            "Known-positive retrieval labels cannot support corpus precision/false-positive rate.",
            "Blocked, mixed, errors and abstentions remain explicitly non-decisions.",
            "Descriptive paired deltas are not a statistical significance test.",
            "External test folds inspected previously cannot count as prospective confirmation.",
        ],
    }
