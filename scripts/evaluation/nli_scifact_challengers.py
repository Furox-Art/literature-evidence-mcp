"""Paired SciFact oracle-rationale NLI stress test: not end-to-end retrieval."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from scripts.evaluation.nli_challenger_benchmark import (
    CANDIDATES,
    infer_model,
    paired_claim_bootstrap,
)
from scripts.evaluation.scifact_nli import example_pairs
from scripts.evaluation.scifact_open_retrieval import HASHES

GOLD_MAP = {"SUPPORT": "Supports", "CONTRADICT": "Refutes"}


def evaluate(folder: Path, model_dirs: dict[str, Path]) -> dict:
    for name, expected in HASHES.items():
        if hashlib.sha256((folder / name).read_bytes()).hexdigest() != expected:
            raise ValueError("SciFact snapshot checksum mismatch")
    examples = example_pairs(folder, "dev")
    if len(examples) != 338:
        raise ValueError("Expected SciFact 338 dev oracle rationale sets")
    data = [
        {"claim": e["hypothesis"], "evidence": e["premise"],
         "label": GOLD_MAP[e["gold"]]} for e in examples
    ]
    gold = [e["gold"] for e in examples]
    ids = [str(e["claim_id"]) for e in examples]
    model_results = {}
    predictions = {}
    for key, path in model_dirs.items():
        if key not in CANDIDATES:
            raise ValueError("Candidate not in pinned model manifest")
        row = infer_model(path, data, CANDIDATES[key]["weights_sha256"])
        pred = row.pop("predictions")
        row.pop("raw_predictions")
        decided = [i for i, x in enumerate(pred) if x != "NEUTRAL"]
        correct = sum(
            (gold[i] == "SUPPORT" and pred[i] == "SUPPORT") or
            (gold[i] == "CONTRADICT" and pred[i] == "REFUTE")
            for i in decided
        )
        row["scifact_gold_rationale_conditional"] = {
            "gold_rationales": len(gold),
            "decided": len(decided),
            "coverage": len(decided) / len(gold),
            "correct_decided": correct,
            "selective_accuracy": correct / len(decided) if decided else None,
            "unconditional_correct": correct / len(gold),
        }
        row["model"] = CANDIDATES[key]
        model_results[key] = row
        predictions[key] = pred
    frozen = "frozen_original_deberta_small"
    if frozen not in predictions:
        raise ValueError("Original reference model missing")
    paired = {
        key: paired_claim_bootstrap(
            ["SUPPORT" if x == "SUPPORT" else "REFUTE" for x in gold],
            pred, predictions[frozen], ids,
        )
        for key, pred in predictions.items() if key != frozen
    }
    return {
        "status": "EXPLORATORY_SCIFACT_GOLD_RATIONALE_NLI_COMPARISON",
        "gold_rationales": len(gold),
        "source_sha256": HASHES,
        "candidate_results": model_results,
        "paired_differences_vs_frozen_original": paired,
        "limitations": [
            "Gold evidence snippets are given, not independently searched or selected.",
            "This dataset has only SUPPORT and CONTRADICT gold evidence, NO gold NEI.",
            ("Models are not fine-tuned on SciFact by the evaluation process; "
             "third-party training provenance cannot be fully independently audited."),
            "Compared datasets are historically visible; no blinded confirmatory selection.",
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
    results = evaluate(args.data, {
        "frozen_original_deberta_small": args.original,
        "fever_anli_deberta_base": args.fever_model,
        "general_deberta_base": args.general_model,
    })
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(results, sort_keys=True, indent=2) + "\n")
    for key, item in results["candidate_results"].items():
        s = item["scifact_gold_rationale_conditional"]
        print(key, "COVERAGE", round(s["coverage"], 5),
              "SELECTIVE_ACC", round(s["selective_accuracy"] or 0, 5),
              "UNCONDITIONAL_CORRECT", round(s["unconditional_correct"], 5))


if __name__ == "__main__":
    main()
