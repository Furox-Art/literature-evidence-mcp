"""Paired, no-training HealthVer NLI candidate audit; NO production model switch.

Models and thresholds are fixed before execution. Due to retrospective TEST
inspection, this is exploratory head-to-head comparison, not a confirmatory
generalization claim or blind model selection.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
from collections import defaultdict
from pathlib import Path

from literature_evidence_mcp.evidence_nli import (
    LABELS,
    MODEL_ID,
    MODEL_REVISION,
    WEIGHTS_SHA256,
    decide,
)
from scripts.evaluation.healthver_nli import (
    GOLD_MAP,
    MARGIN,
    SHA,
    THRESHOLD,
    norm,
    read_rows,
    selective,
    three_way,
)

CANDIDATES = {
    "fever_anli_deberta_base": {
        "id": "MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli",
        "revision": "6f5cf0a2b59cabb106aca4c287eed12e357e90eb",
        "license": "mit",
        "weights_sha256": "06d6fd89edd4f97816831626daafbdb0b029cf63bae8edc0bccab1d64e2e7707",
    },
    "general_deberta_base": {
        "id": "cross-encoder/nli-deberta-v3-base",
        "revision": "6c749ce3425cd33b46d187e45b92bbf96ee12ec7",
        "license": "apache-2.0",
        "weights_sha256": "d8148c6d49e0a7925134294c56326c71fe0ab1dc390e37355e00c7efbb488afa",
    },
    "frozen_original_deberta_small": {
        "id": MODEL_ID,
        "revision": MODEL_REVISION,
        "license": "apache-2.0",
        "weights_sha256": WEIGHTS_SHA256,
    },
}
ARGMAX = {"entailment": "SUPPORT", "contradiction": "REFUTE", "neutral": "NEUTRAL"}
DECISION = {"PREDICTED_SUPPORT": "SUPPORT",
            "PREDICTED_REFUTE": "REFUTE",
            "INSUFFICIENT_MODEL_EVIDENCE": "NEUTRAL"}


def verify_class_labels(config) -> dict[int, str]:
    """Reject ambiguous or duplicate class IDs instead of silently reversing labels."""
    found = {int(k): str(v).lower() for k, v in config.id2label.items()}
    if set(found) != {0, 1, 2} or set(found.values()) != set(LABELS):
        raise ValueError("Unexpected NLI class order or unmapped classes")
    return found


def verify_weights(path: Path, expected: str | None = None) -> str:
    file = path / "model.safetensors"
    if not file.is_file():
        raise FileNotFoundError("Pinned safetensors missing")
    with file.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    if expected is not None and digest != expected:
        raise ValueError("Model weights SHA-256 mismatch")
    return digest


def infer_model(model_dir: Path, data: list[dict], label_expected: str | None = None) -> dict:
    """Never invoke network or load untrusted model-specific code."""
    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    weight_sha = verify_weights(model_dir, label_expected)
    tokenizer = AutoTokenizer.from_pretrained(
        str(model_dir), local_files_only=True, trust_remote_code=False,
    )
    model = AutoModelForSequenceClassification.from_pretrained(
        str(model_dir), local_files_only=True, trust_remote_code=False,
        use_safetensors=True,
    )
    mapping = verify_class_labels(model.config)
    device = os.environ.get("LITERATURE_EVIDENCE_NLI_DEVICE", "cpu")
    if device not in {"cpu", "cuda"} or (device == "cuda" and not torch.cuda.is_available()):
        raise ValueError("Invalid or unavailable compute device")
    model.eval().to(device)
    gold = [GOLD_MAP[row["label"]] for row in data]
    preds = []
    raw_predictions = []
    confidences = []
    errors = []
    batch_size = 16 if device == "cuda" else 8
    for start in range(0, len(data), batch_size):
        batch = data[start:start + batch_size]
        encoded = tokenizer(
            [row["evidence"] for row in batch], [row["claim"] for row in batch],
            padding=True, truncation=True, max_length=512, return_tensors="pt",
        )
        encoded = {name: value.to(device) for name, value in encoded.items()}
        with torch.inference_mode():
            logits = model(**encoded).logits
            prob_matrix = torch.softmax(logits, dim=-1).cpu().tolist()
        for row in prob_matrix:
            probabilities = {mapping[k]: float(prob) for k, prob in enumerate(row)}
            # Original frozen production mapping, no fitted new rule.
            predicted = DECISION[decide(probabilities, THRESHOLD, MARGIN)]
            raw = ARGMAX[max(LABELS, key=lambda k: probabilities[k])]
            preds.append(predicted)
            raw_predictions.append(raw)
            confidences.append(max(probabilities.values()))
            errors.append(sum((probabilities[k] - (ARGMAX[k] == gold[len(preds) - 1])) ** 2
                              for k in LABELS))
    del model
    if device == "cuda":
        torch.cuda.empty_cache()
    # Rank-order invariance of synthetic controls is tested separately.
    n = len(data)
    assert len(preds) == n
    return {
        "weights_sha256": weight_sha,
        "label_mapping": {str(k): val for k, val in mapping.items()},
        "predictions": preds,
        "raw_predictions": raw_predictions,
        "mean_multiclass_brier_score": sum(errors) / n,
        "mean_top_softmax": sum(confidences) / n,
        "metrics": three_way(gold, preds),
        "raw_argmax_metrics": three_way(gold, raw_predictions),
        "selective": selective(gold, preds),
    }


def paired_claim_bootstrap(
    truth: list[str], first: list[str], second: list[str],
    claims: list[str], repeats: int = 500,
) -> dict:
    """Cluster by claim; same clusters sampled for both predictions."""
    if not truth or len(set(map(len, (truth, first, second, claims)))) != 1:
        raise ValueError("Paired vectors must have equal nonzero lengths")
    groups: dict[str, list[int]] = defaultdict(list)
    for i, c in enumerate(claims):
        groups[c].append(i)
    keys = sorted(groups)
    rng = random.Random(20261018)
    values = []
    for _ in range(repeats):
        indices = [i for key in rng.choices(keys, k=len(keys)) for i in groups[key]]
        n = len(indices)
        difference = sum(truth[i] == first[i] for i in indices) / n - sum(
            truth[i] == second[i] for i in indices) / n
        values.append(difference)
    sorted_values = sorted(values)
    return {
        "accuracy_difference": sum(truth[i] == first[i] for i in range(len(truth))) / len(truth)
        - sum(truth[i] == second[i] for i in range(len(truth))) / len(truth),
        "paired_claim_cluster_bootstrap_95pct": [
            round(sorted_values[int(.025 * repeats)], 5),
            round(sorted_values[int(.975 * repeats)], 5),
        ],
    }


def evaluate(data_folder: Path, model_dirs: dict[str, Path]) -> dict:
    for part, sha in SHA.items():
        file = data_folder / f"healthver_{part}.csv"
        if hashlib.sha256(file.read_bytes()).hexdigest() != sha:
            raise ValueError("HealthVer gold snapshot mismatch")
    # No training or DEV fit, only verify presence and source hash.
    test = read_rows(data_folder, "test")
    if len(test) != 1823:
        raise ValueError("Unexpected HealthVer held-out TEST rows")
    truth = [GOLD_MAP[row["label"]] for row in test]
    ids = [norm(row["claim"]) for row in test]
    first_pairs: dict[tuple[str, str], int] = {}
    for i, row in enumerate(test):
        pair = (norm(row["claim"]), norm(row["evidence"]))
        if pair in first_pairs and truth[i] != truth[first_pairs[pair]]:
            raise ValueError("Conflicting gold labels on duplicate pairs")
        first_pairs.setdefault(pair, i)
    unique = list(first_pairs.values())
    if len(unique) != 1694:
        raise ValueError("Unexpected number of repeated claim-evidence pairs")
    scores = {}
    responses = {}
    for key, directory in model_dirs.items():
        if key not in CANDIDATES:
            raise ValueError("Unknown unpinned model")
        result = infer_model(directory, test, CANDIDATES[key].get("weights_sha256"))
        predictions = result.pop("predictions")
        raw = result.pop("raw_predictions")
        result["unique_pair_metrics"] = three_way(
            [truth[i] for i in unique], [predictions[i] for i in unique])
        result["support_recall"] = result["metrics"]["per_class"]["SUPPORT"]["recall"]
        result["candidate"] = CANDIDATES[key]
        result["raw_argmax_neutral_count"] = sum(x == "NEUTRAL" for x in raw)
        scores[key] = result
        responses[key] = predictions
    if "frozen_original_deberta_small" not in scores:
        raise ValueError("The original production model must be benchmarked too")
    baseline = "frozen_original_deberta_small"
    paired = {
        key: paired_claim_bootstrap(truth, pred, responses[baseline], ids)
        for key, pred in responses.items() if key != baseline
    }
    return {
        "status": "EXPLORATORY_PINNED_MODEL_COMPARISON_NOT_PRODUCTION_SELECTION",
        "dataset": "HealthVer human-labeled held-out TEST (already previously inspected)",
        "dataset_sha256": SHA,
        "test_size": len(test), "unique_test_pairs": len(unique),
        "candidate_results": scores,
        "paired_differences_vs_frozen_production": paired,
        "evaluation": "Zero-shot, same ordered text pairs, same 0.70 confidence / 0.15 margin, "
                      "no model tuning and no training on HealthVer by this project.",
        "selection_disclaimer": "This reused previously inspected TEST labels for exploratory "
                                "comparisons; selecting a winning model here would require fresh "
                                "independent confirmation before production promotion.",
        "limitations": [
            "No new model has been deployed in the MCP server.",
            "Test samples include 129 duplicate exact pairs; unique-pair sensitivity included.",
            "Source passages are gold-supplied; source authenticity and retrieval untested.",
            "Medical reliability, causality, RoB, and real evidence insufficiency unproven.",
            ("Separate MedNLI/SciFact training provenance claims derive from model cards, "
             "not an audited full training manifest."),
            "Uncalibrated softmax scores are not probabilities of scientific truth.",
            "Repeated retrospective HealthVer test comparison is not blinded scientific confirmation.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--original", type=Path, required=True)
    parser.add_argument("--fever-model", type=Path, required=True)
    parser.add_argument("--general-model", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = evaluate(args.data, {
        "frozen_original_deberta_small": args.original,
        "fever_anli_deberta_base": args.fever_model,
        "general_deberta_base": args.general_model,
    })
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n")
    for key, m in result["candidate_results"].items():
        print(key, "ACC", round(m["metrics"]["accuracy"], 5),
              "F1", round(m["metrics"]["macro_f1"], 5),
              "SUPPORT_RECALL", round(m["support_recall"], 5),
              "UNIQUE_ACC", round(m["unique_pair_metrics"]["accuracy"], 5))


if __name__ == "__main__":
    main()
