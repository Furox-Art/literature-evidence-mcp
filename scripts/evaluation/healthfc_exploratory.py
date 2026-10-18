"""HealthFC external, explicitly exploratory NLI comparison of fixed syntax-only subset.

The downloaded CC BY-NC-ND corpus and transformed strings remain on the
temporary runner; this writes only aggregate model metrics. Not confirmatory.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from scripts.evaluation.healthfc_controlled import prepare, read_source
from scripts.evaluation.nli_challenger_benchmark import (
    CANDIDATES,
    infer_model,
    paired_claim_bootstrap,
)

FROZEN_COUNT = 511
FROZEN_LABELS = {"SUPPORT": 136, "REFUTE": 89, "NEUTRAL": 286}
BASELINE = "frozen_original_deberta_small"
LABEL = {"Supports": "SUPPORT", "Refutes": "REFUTE", "Neutral": "NEUTRAL"}


def evaluate(source: Path, model_dirs: dict[str, Path]) -> dict:
    """No training, calibration, class thresholds or model selection."""
    rows = read_source(source)
    selection, audit = prepare(rows)
    if (audit["selected_rows"] != FROZEN_COUNT or
            audit["selected_label_distribution"] != FROZEN_LABELS):
        raise ValueError("HealthFC frozen syntax-only cohort changed")
    if set(model_dirs) != set(CANDIDATES):
        raise ValueError("All 3 fixed models are required for paired comparison")
    truth = [LABEL[r["label"]] for r in selection]
    ids = [row["claim"] for row in selection]
    results = {}
    predictions = {}
    for candidate, folder in model_dirs.items():
        score = infer_model(folder, selection, CANDIDATES[candidate]["weights_sha256"])
        pred = score.pop("predictions")
        score.pop("raw_predictions")
        score["candidate"] = CANDIDATES[candidate]
        results[candidate] = score
        predictions[candidate] = pred
    paired = {
        key: paired_claim_bootstrap(truth, prediction, predictions[BASELINE], ids)
        for key, prediction in predictions.items() if key != BASELINE
    }
    return {
        "status": "EXPLORATORY_SYNTAX_ONLY_TRANSFORMATION_NOT_EXPERT_ADJUDICATED",
        "dataset": "HealthFC (expert fact-check labels; external retrospective source)",
        "cohort_audit": audit,
        "candidate_results": results,
        "paired_differences_vs_original": paired,
        "method": (
            "Only syntactically supported English closed questions were inverted to "
            "affirmative hypotheses, without editing gold labels or evidence snippets. "
            "Premises are gold-selected top sentences. Fixed 0.70/0.15 decision rule."
        ),
        "limitations": [
            "This is NOT blinded prospective confirmation of NLI generalization.",
            "No expert has checked equivalence of all transformed claims.",
            "HealthFC label NEI is about clinical evidence sufficiency, not textual NLI neutral.",
            "Some HealthFC expert verdicts can be outdated; source ends 2022.",
            "No guarantee that all checkpoints did not pretrain on this public dataset.",
            "The selected subset excludes 239 items and is nonrandom.",
            "Up to five gold-selected article sentences are not independently retrieved.",
            "No patient-facing, causal, scientific-truth or production reliability claim.",
            "The transformed and original licensed content is never published.",
        ],
        "selection_policy": "NO_PRODUCTION_SELECTION_BASED_ON_EXPLORATORY_METRICS",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--original", type=Path, required=True)
    parser.add_argument("--fever-model", type=Path, required=True)
    parser.add_argument("--general-model", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = evaluate(args.source, {
        BASELINE: args.original,
        "fever_anli_deberta_base": args.fever_model,
        "general_deberta_base": args.general_model,
    })
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, sort_keys=True, indent=2) + "\n")
    print("Retained syntactically converted cases:",
          report["cohort_audit"]["selected_rows"])
    for key, item in report["candidate_results"].items():
        print(key, "accuracy", round(item["metrics"]["accuracy"], 5),
              "macro_f1", round(item["metrics"]["macro_f1"], 5),
              "support_recall",
              round(item["metrics"]["per_class"]["SUPPORT"]["recall"], 5))
    print("Exploratory, no expert meaning-equivalence verification or model promotion")


if __name__ == "__main__":
    main()
