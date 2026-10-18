"""Pin measured external gold report; never treat abstentions as correct gold NEI."""
from __future__ import annotations

import json
from pathlib import Path

from literature_evidence_mcp.evidence_nli import MODEL_REVISION, WEIGHTS_SHA256


def test_external_gold_counts_and_honest_limits():
    report = json.loads((Path(__file__).resolve().parents[1] /
                         "reports/evaluation/scifact_nli_dev.json").read_text())
    assert report["model_revision"] == MODEL_REVISION
    assert report["model_safetensors_sha256"] == WEIGHTS_SHA256
    assert report["gold_dev_rationales"] == 338
    assert report["nli_zero_shot_gold_rationale_results"]["count"] == 338
    measured = report["nli_zero_shot_gold_rationale_results"]
    assert measured["predicted_support"] + measured["predicted_refute"] + measured["abstained"] == 338
    assert measured["abstained"] > 0
    assert measured["selective_accuracy_given_prediction"] < 1.0
    assert measured["coverage"] < 1.0
    assert measured["unconditional_correct_over_all_gold_rationales"] < (
        report["train_only_majority_baseline_results"]["unconditional_correct_over_all_gold_rationales"])
    assert report["no_independent_gold_for_insufficient_class"] is True
    assert report["gold_is_given_not_retrieved"] is True
    assert report["not_validated_scientific_truth"] is True
    assert report["selection"]["uses_dev_for_threshold_selection"] is False
