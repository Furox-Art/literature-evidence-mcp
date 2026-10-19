"""Full-public-test exploratory VitaminC NLI comparison, no training/tuning.

Reuses the three already frozen HealthVer/SciFact NLI checkpoints and
0.70/0.15 decision gate; maps VitaminC NOT ENOUGH INFO to textual NEUTRAL
as a cross-domain proxy (not a clinical truth determination). Reports only
aggregate, source-pinned metrics; licensed rows/predictions never published.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

from scripts.evaluation.healthver_nli import GOLD_MAP, three_way
from scripts.evaluation.nli_challenger_benchmark import CANDIDATES, infer_model
from scripts.evaluation.pin_dual_track_candidate_sources import CANDIDATES as DATASETS

GOLD_LABELS = {
    "SUPPORTS": "Supports",
    "REFUTES": "Refutes",
    "NOT ENOUGH INFO": "Neutral",
}
EXPECTED_ROWS = 55197


def read_vitaminc(source: Path) -> tuple[list[dict], list[str]]:
    if hashlib.sha256(source.read_bytes()).hexdigest() != DATASETS["classification"]["sha256"]:
        raise ValueError("VitaminC frozen source SHA-256 mismatch")
    rows = []
    groups = []
    unique_ids = set()
    with source.open(encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            row = json.loads(line)
            if not isinstance(row, dict) or row.get("label") not in GOLD_LABELS:
                raise ValueError("Unknown VitaminC gold label")
            if (not isinstance(row.get("claim"), str) or
                    not isinstance(row.get("evidence"), str) or
                    not row["claim"].strip() or not row["evidence"].strip()):
                raise ValueError("Empty or invalid VitaminC sentence pair")
            uid = row.get("unique_id")
            case_id = row.get("case_id")
            if (not isinstance(uid, str) or not uid or uid in unique_ids
                    or not isinstance(case_id, str) or not case_id):
                raise ValueError("Missing or duplicated VitaminC identifier")
            unique_ids.add(uid)
            rows.append({
                "claim": row["claim"],
                "evidence": row["evidence"],
                "label": GOLD_LABELS[row["label"]],
            })
            groups.append(case_id)
    if len(rows) != EXPECTED_ROWS:
        raise ValueError("Unexpected VitaminC test row count")
    return rows, groups


def summarize(model_key: str, model_dir: Path, rows: list[dict], groups: list[str]) -> dict:
    if model_key not in CANDIDATES:
        raise ValueError("Only pre-pinned NLI candidates are allowed")
    if not rows or len(rows) != len(groups):
        raise ValueError("Invalid or unmatched prepared VitaminC cases")
    result = infer_model(model_dir, rows, CANDIDATES[model_key]["weights_sha256"])
    preds = result.pop("predictions")
    raw = result.pop("raw_predictions")
    if len(preds) != len(rows) or len(raw) != len(rows):
        raise ValueError("Model output and gold rows misaligned")
    truth = [GOLD_MAP[row["label"]] for row in rows]
    # Same fixed order. Unique-pair sensitivity is descriptive, not a new test.
    seen = set()
    unique = []
    for i, r in enumerate(rows):
        pair = (r["claim"].casefold().strip(), r["evidence"].casefold().strip())
        if pair not in seen:
            unique.append(i)
            seen.add(pair)
    result["unique_pair_metrics"] = three_way(
        [truth[i] for i in unique], [preds[i] for i in unique]
    )
    result["duplicate_exact_pairs"] = len(rows) - len(unique)
    result["case_id_groups"] = len(set(groups))
    result["model"] = CANDIDATES[model_key]
    result["model_key"] = model_key
    result["raw_argmax_predictions_count"] = dict(sorted(Counter(raw).items()))
    result["decision_predictions_count"] = dict(sorted(Counter(preds).items()))
    result["status"] = "EXPLORATORY_RETROSPECTIVE_CROSS_DOMAIN_NOT_CLINICAL_VALIDATION"
    result["dataset"] = "VitaminC pinned public test"
    result["dataset_sha256"] = DATASETS["classification"]["sha256"]
    result["test_rows"] = len(rows)
    result["gold_label_mapping"] = {
        "SUPPORTS": "SUPPORT", "REFUTES": "REFUTE",
        "NOT ENOUGH INFO": "NEUTRAL (exploratory semantic proxy)",
    }
    result["scientific_superiority_demonstrated"] = False
    result["production_model_modified"] = False
    result["limitations"] = [
        "Public retrospective VitaminC can overlap unseen model pretraining datasets.",
        "Wikipedia edit claim-evidence pairs are not biomedical or clinical evidence.",
        "Gold NOT ENOUGH INFO is not automatically equivalent to semantic NLI neutral.",
        "Frozen 0.70/0.15 rule mixes semantic neutral and low-confidence abstention.",
        "All three historical models and hyperparameters were pinned before this run.",
        "No comparison to commercial competitors or independent blind expert review.",
        "Per-case text/predictions remain in the ephemeral execution environment only.",
        "No causal, patient-facing, superiority, calibration, or deployment claim.",
    ]
    return result


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--dataset", type=Path, required=True)
    p.add_argument("--model-key", choices=sorted(CANDIDATES), required=True)
    p.add_argument("--model-dir", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    rows, groups = read_vitaminc(args.dataset)
    print("VITAMINC_INPUT_VERIFIED", len(rows), "MODEL", args.model_key, flush=True)
    result = summarize(args.model_key, args.model_dir, rows, groups)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n")
    print("VITAMINC_MODEL_COMPLETED", args.model_key,
          "accuracy", round(result["metrics"]["accuracy"], 5),
          "macro_f1", round(result["metrics"]["macro_f1"], 5), flush=True)


if __name__ == "__main__":
    main()
