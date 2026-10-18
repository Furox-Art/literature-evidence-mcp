"""Strict holdout HealthVer three-way NLI check: no training or test tuning.

The model, threshold and margins are frozen BEFORE this dataset evaluation.
Use caller-supplied HealthVer evidence, so results are not evidence retrieval.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
from collections import Counter, defaultdict
from pathlib import Path

from literature_evidence_mcp.evidence_nli import (
    LABELS,
    MODEL_ID,
    MODEL_REVISION,
    WEIGHTS_SHA256,
    decide,
    scores_for_pairs,
)

REVISION = "b20ac99ceed62f5264a319fa25a854df1668d85b"
SHA = {
    "train": "57668949f79d0f46e66d74df4b0bc9812cad4d5ad7c5dd03dfba008a608b3f2a",
    "dev": "6f8ea31cbcf2ea5a2d3c82d65587d66e96de4f70e72642bbf7f61fec6ef8a93a",
    "test": "cf457d2dcddd7a736408082d0037527884f7ca3bda06729e1da5ec9e3b135819",
}
GOLD_MAP = {"Supports": "SUPPORT", "Refutes": "REFUTE", "Neutral": "NEUTRAL"}
PRED_MAP = {"PREDICTED_SUPPORT": "SUPPORT", "PREDICTED_REFUTE": "REFUTE",
            "INSUFFICIENT_MODEL_EVIDENCE": "NEUTRAL"}
CLASSES = ("SUPPORT", "REFUTE", "NEUTRAL")
THRESHOLD, MARGIN = 0.70, 0.15


def read_rows(folder: Path, name: str) -> list[dict]:
    source = folder / f"healthver_{name}.csv"
    if hashlib.sha256(source.read_bytes()).hexdigest() != SHA[name]:
        raise ValueError("HealthVer SHA-256 mismatch: " + name)
    with source.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    if not rows or any(
        not row["claim"].strip() or not row["evidence"].strip() or
        row["label"] not in GOLD_MAP for row in rows
    ):
        raise ValueError("Malformed HealthVer gold row")
    return rows


def norm(text: str) -> str:
    return " ".join(text.casefold().split())


def three_way(gold: list[str], predictions: list[str]) -> dict:
    if len(gold) != len(predictions) or not gold:
        raise ValueError("mismatched or empty gold/predictions")
    if any(item not in CLASSES for item in gold+predictions):
        raise ValueError("unknown three-way class")
    confusion = {g: {p: sum(a == g and b == p for a, b in zip(gold, predictions))
                     for p in CLASSES} for g in CLASSES}
    f1 = {}
    precision = {}
    recall = {}
    for cls in CLASSES:
        tp = confusion[cls][cls]
        predicted = sum(confusion[g][cls] for g in CLASSES)
        actual = sum(confusion[cls].values())
        precision[cls] = tp / predicted if predicted else 0.0
        recall[cls] = tp / actual if actual else 0.0
        f1[cls] = 2 * tp / (predicted + actual) if predicted + actual else 0.0
    accuracy = sum(g == p for g, p in zip(gold, predictions)) / len(gold)
    return {
        "count": len(gold),
        "label_distribution": dict(sorted(Counter(gold).items())),
        "prediction_distribution": dict(sorted(Counter(predictions).items())),
        "confusion": confusion,
        "accuracy": accuracy,
        "balanced_accuracy": sum(recall.values()) / 3,
        "macro_f1": sum(f1.values()) / 3,
        "per_class": {cls: {"precision": precision[cls], "recall": recall[cls],
                            "f1": f1[cls]} for cls in CLASSES},
    }


def selective(gold: list[str], predictions: list[str]) -> dict:
    selected = [i for i, label in enumerate(predictions) if label != "NEUTRAL"]
    correct = sum(gold[i] == predictions[i] for i in selected)
    neutral_correct = sum(g == p == "NEUTRAL" for g, p in zip(gold, predictions))
    return {
        "non_neutral_coverage": len(selected) / len(gold),
        "accuracy_given_non_neutral_prediction": correct / len(selected) if selected else None,
        "non_neutral_correct_out_of_all": correct / len(gold),
        "neutral_class_correct_out_of_all": neutral_correct / len(gold),
        "warning": "NEUTRAL blends model neutral softmax and low-confidence abstention; "
                   "it cannot be assumed to mean evidence is truly insufficient.",
    }


def bootstrap(gold: list[str], prediction: list[str], claim_ids: list[str],
              repeats: int = 500) -> dict:
    if len(gold) != len(claim_ids):
        raise ValueError("group-label mismatch")
    by_claim: dict[str, list[int]] = defaultdict(list)
    for i, claim in enumerate(claim_ids):
        by_claim[claim].append(i)
    keys = sorted(by_claim)
    rng = random.Random(20261018)
    out = {"accuracy": [], "macro_f1": [], "balanced_accuracy": []}
    for _ in range(repeats):
        chosen = [i for key in rng.choices(keys, k=len(keys)) for i in by_claim[key]]
        result = three_way([gold[i] for i in chosen], [prediction[i] for i in chosen])
        for metric, values in out.items():
            values.append(result[metric])
    return {name: [round(x, 5) for x in
                   (sorted(values)[int(repeats * .025)],
                    sorted(values)[int(repeats * .975)])]
            for name, values in out.items()}


def classify_decision_origin(scores: dict[str, float]) -> str:
    """Explain current frozen abstention rule; NOT a newly fitted classifier."""
    order = sorted(LABELS, key=lambda label: scores[label], reverse=True)
    if order[0] == "neutral":
        return "neutral_argmax"
    if scores[order[0]] < THRESHOLD:
        return "directional_below_threshold"
    if scores[order[0]] - scores[order[1]] < MARGIN:
        return "directional_below_margin"
    return "directional_decision"


def label_diagnostics(gold: list[str], probs: list[dict[str, float]],
                      predictions: list[str]) -> dict:
    """Assess actual neutral softmax vs confidence abstention, no threshold tuning."""
    if len(gold) != len(probs) or len(gold) != len(predictions) or not gold:
        raise ValueError("NLI diagnostic vectors must align and be nonempty")
    # Validate every probability vector through the frozen production rule.
    for item in probs:
        decide(item, THRESHOLD, MARGIN)
    origins = [classify_decision_origin(item) for item in probs]
    raw_map = {"entailment": "SUPPORT", "contradiction": "REFUTE",
               "neutral": "NEUTRAL"}
    raw_pred = [raw_map[max(LABELS, key=lambda label: p[label])] for p in probs]
    mismatch = [i for i, origin in enumerate(origins)
                if (origin == "directional_decision") != (predictions[i] != "NEUTRAL")]
    if mismatch:
        raise ValueError("Diagnostic diverges from the frozen production decision")
    explanation = {}
    for key in ("neutral_argmax", "directional_below_threshold",
                "directional_below_margin", "directional_decision"):
        matching = [i for i, origin in enumerate(origins) if origin == key]
        explanation[key] = {
            "count": len(matching),
            "gold_distribution": dict(sorted(Counter(gold[i] for i in matching).items())),
        }
    # True three-label softmax scoring before mixing abstentions into NEUTRAL.
    brier = 0.0
    bins = [{"count": 0, "confidence_sum": 0.0, "correct": 0}
            for _ in range(10)]
    for truth, probability, guessed in zip(gold, probs, raw_pred):
        if not all(label in probability for label in LABELS):
            raise ValueError("Missing softmax class")
        actual_probs = {raw_map[key]: probability[key] for key in LABELS}
        if any(not 0 <= val <= 1 for val in actual_probs.values()):
            raise ValueError("Invalid softmax scores")
        brier += sum((actual_probs[label] - (truth == label)) ** 2
                     for label in CLASSES)
        confidence = max(probability.values())
        index = min(int(confidence * 10), 9)
        bins[index]["count"] += 1
        bins[index]["confidence_sum"] += confidence
        bins[index]["correct"] += truth == guessed
    n = len(gold)
    ece = sum(abs(row["confidence_sum"] / row["count"]
                  - row["correct"] / row["count"]) * row["count"] / n
              for row in bins if row["count"])
    return {
        "decision_origin": explanation,
        "argmax_three_class_metrics_without_abstention_mapping": three_way(gold, raw_pred),
        "brier_score_multiclass_uncalibrated": brier / n,
        "expected_calibration_error_10_bins_descriptive": ece,
        "confidence_bins": [
            {"lower_inclusive": k / 10, "upper_exclusive_except_last": (k + 1) / 10,
             "n": row["count"],
             "mean_top_softmax": row["confidence_sum"] / row["count"] if row["count"] else None,
             "empirical_top1_accuracy": row["correct"] / row["count"] if row["count"] else None}
            for k, row in enumerate(bins)
        ],
        "interpretation": "Model softmax is not calibrated factual confidence. "
            "A NEUTRAL gold label does not validate generic abstention, "
            "and argmax neutral is distinct from a directional low-confidence refusal.",
    }


def topic_diagnostics(test: list[dict], gold: list[str],
                      predictions: list[str], minimum: int = 30) -> dict:
    """Group by the dataset's own topic identifier, suppress tiny groups."""
    if not (len(test) == len(gold) == len(predictions)):
        raise ValueError("Topic vectors differ in size")
    groups: dict[str, list[int]] = defaultdict(list)
    for index, row in enumerate(test):
        groups[str(row["topic_ip"])].append(index)
    included = {}
    suppressed = {}
    for group, indices in sorted(groups.items()):
        if len(indices) < minimum:
            suppressed[group] = len(indices)
            continue
        result = three_way([gold[i] for i in indices],
                           [predictions[i] for i in indices])
        included[group] = {
            "n": len(indices), "accuracy": result["accuracy"],
            "macro_f1": result["macro_f1"],
            "support_recall": result["per_class"]["SUPPORT"]["recall"],
            "label_distribution": result["label_distribution"],
        }
    return {
        "min_rows_per_reported_topic": minimum,
        "included": included, "suppressed_topic_counts": suppressed,
        "warning": "Subgroups use original dataset topic IDs and may overlap "
                   "by claim; exploratory, no multiple-testing correction.",
    }


def evaluate(folder: Path, model_folder: Path) -> dict:
    import os

    train, dev, test = [read_rows(folder, name) for name in ("train", "dev", "test")]
    train_labels = Counter(GOLD_MAP[x["label"]] for x in train)
    majority = train_labels.most_common(1)[0][0]
    train_claims = {norm(x["claim"]) for x in train}
    test_claims = {norm(x["claim"]) for x in test}
    dev_claims = {norm(x["claim"]) for x in dev}
    pairs = [(norm(x["claim"]), norm(x["evidence"])) for x in test]
    first_occurrence = {}
    conflicting_duplicate_labels = 0
    for ix, pair in enumerate(pairs):
        if pair in first_occurrence:
            old_ix = first_occurrence[pair]
            conflicting_duplicate_labels += test[ix]["label"] != test[old_ix]["label"]
        else:
            first_occurrence[pair] = ix
    if conflicting_duplicate_labels:
        raise ValueError("Gold label disagreement between identical test pairs")
    if len(test) != 1823 or len(first_occurrence) != 1694:
        raise ValueError("Unexpected HealthVer TEST partition or duplicated pair count")
    os.environ["LITERATURE_EVIDENCE_NLI_MODEL_DIR"] = str(model_folder)
    probs = scores_for_pairs([(row["evidence"], row["claim"]) for row in test])
    predicted = [PRED_MAP[decide(score, THRESHOLD, MARGIN)] for score in probs]
    truth = [GOLD_MAP[x["label"]] for x in test]
    diagnostics = label_diagnostics(truth, probs, predicted)
    topics = topic_diagnostics(test, truth, predicted)
    baseline = [majority] * len(test)
    by_pair = sorted(first_occurrence.values())
    dedup_truth = [truth[i] for i in by_pair]
    dedup_pred = [predicted[i] for i in by_pair]
    model_sha = hashlib.sha256((model_folder / "model.safetensors").read_bytes()).hexdigest()
    if model_sha != WEIGHTS_SHA256:
        raise ValueError("Not the pinned safetensors weight blob")
    return {
        "status": "EXTERNAL_THREE_CLASS_HEALTHVER_TEST_COMPLETE_WITH_LIMITATIONS",
        "dataset": "HealthVer (Sarrouti et al., Findings EMNLP 2021)",
        "url": "https://github.com/sarrouti/HealthVer",
        "revision": REVISION, "source_sha256": SHA,
        "original_license": "No explicit repository LICENSE detected; do not redistribute source CSV.",
        "split": {"train_rows": len(train), "dev_rows": len(dev),
                  "test_rows": len(test), "unique_test_pairs": len(first_occurrence),
                  "unique_test_claims": len(test_claims),
                  "train_test_exact_claim_overlaps": len(train_claims & test_claims),
                  "dev_test_exact_claim_overlaps": len(dev_claims & test_claims),
                  "repeated_test_rows": len(test)-len(first_occurrence)},
        "model": MODEL_ID, "model_revision": MODEL_REVISION,
        "model_weights_sha256": model_sha,
        "model_fitted_on_healthver": False,
        "test_label_based_threshold_selection": False,
        "frozen_threshold": THRESHOLD, "frozen_margin": MARGIN,
        "label_mapping": GOLD_MAP, "predicted_mapping": PRED_MAP,
        "test_metrics_all_rows": three_way(truth, predicted),
        "test_selective_metrics": selective(truth, predicted),
        "neutral_and_abstention_diagnostics": diagnostics,
        "topic_stratified_exploratory": topics,
        "test_claim_cluster_bootstrap_95pct": bootstrap(
            truth, predicted, [norm(r["claim"]) for r in test]),
        "deduplicated_test_metrics": three_way(dedup_truth, dedup_pred),
        "exact_train_claim_overlap_excluded_sensitivity": three_way(
            [truth[i] for i, row in enumerate(test)
             if norm(row["claim"]) not in train_claims],
            [predicted[i] for i, row in enumerate(test)
             if norm(row["claim"]) not in train_claims]),
        "train_majority_label_baseline": {
            "label": majority, "test": three_way(truth, baseline)},
        "always_neutral_baseline": three_way(truth, ["NEUTRAL"] * len(test)),
        "limitations": [
            "This is a separate real human-annotated three-way TEST set, not expert clinical validation.",
            "The same pre-existing SciFact frozen NLI model and 0.70/0.15 thresholds were used.",
            "Neutral classifier predictions and low-confidence abstentions both map to NEUTRAL.",
            "Provided evidence passages, not retrieved or publisher-authenticated articles.",
            "Contains 129 repeated identical claim-evidence pairs; deduplicated sensitivity shown.",
            "One exact test claim also exists in HealthVer train, but this model never trains on HealthVer.",
            "No RoB/GRADE, causal inference, medical safety, or full scientific truth claims.",
            "Published HealthVer leaderboard systems used HealthVer training; direct performance superiority comparison is invalid.",
            "Topic and calibration summaries are exploratory and do not tune model decisions.",
            "Argmax NEUTRAL and non-neutral low-confidence abstentions are not synonymous.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = evaluate(args.data, args.model_dir)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n")
    print("HEALTHVER_TEST", json.dumps({
        "rows": result["split"]["test_rows"],
        "unique_pairs": result["split"]["unique_test_pairs"],
        "metric": result["test_metrics_all_rows"]["macro_f1"],
        "accuracy": result["test_metrics_all_rows"]["accuracy"],
        "neutral_f1": result["test_metrics_all_rows"]["per_class"]["NEUTRAL"]["f1"],
        "majority_accuracy": result["train_majority_label_baseline"]["test"]["accuracy"],
        "selective": result["test_selective_metrics"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
