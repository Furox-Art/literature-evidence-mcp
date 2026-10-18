# Experimental offline NLI claim-evidence triage

**This is NOT a certified scientific fact-checker.** The opt-in
`nli_assess_evidence` MCP tool estimates whether a **user-supplied evidence
passage** supports, refutes, or is insufficient for a **user-supplied claim**.
Predictions are explicitly provisional, not facts or ground-truth decisions.
It does not search the corpus or independently authenticate publisher material.

## Model and provenance

- Base: `cross-encoder/nli-deberta-v3-small` (Apache-2.0; SNLI+MultiNLI).
- Frozen Hugging Face revision:
  `fa2804872c3b4bd748f38c0185cc85775361e735`.
- Frozen `model.safetensors` SHA-256:
  `ebc79588dd73ccfb6a3f6078519cfbf512c5305384c5ea1845bc71cd32216e86`.
- Inputs are never sent to hosted inference APIs. The model must be
  downloaded explicitly to a local directory. Runtime sets
  `trust_remote_code=False`, `local_files_only=True`, and
  `use_safetensors=True`; weight hash and three-class label map are validated.
- The system's original search, citation, quote and risk-of-bias tools remain
  unchanged. No new default Python dependencies or npm Registry publication.

## Install and run (explicitly optional)

```bash
python -m pip install -e '.[nli]'
python - <<'PY'
from huggingface_hub import snapshot_download
snapshot_download(
    'cross-encoder/nli-deberta-v3-small',
    revision='fa2804872c3b4bd748f38c0185cc85775361e735',
    local_dir='/tmp/literature-nli-small',
    allow_patterns=['*.json', '*.safetensors', 'spm.model', '*.txt'],
)
PY
export LITERATURE_EVIDENCE_NLI_MODEL_DIR=/tmp/literature-nli-small
```

`nli_assess_evidence` arguments: `claim`, `evidence`, `source_id`,
optional `threshold=0.70` and `margin=0.15`. Labels:
`PREDICTED_SUPPORT`, `PREDICTED_REFUTE`,
`INSUFFICIENT_MODEL_EVIDENCE`. Raw model softmax values are **not
calibrated probabilities that a scientific assertion is true**.
The threshold and margin were fixed **before SciFact DEV evaluation**.

No configured local model: `LOCAL_MODEL_NOT_CONFIGURED`; no model files:
`LOCAL_MODEL_FILES_MISSING`; dependencies missing:
`OPTIONAL_NLI_DEPENDENCY_MISSING`. Each yields insufficient evidence rather
than a fabricated judgment. For sensitive claims, use expert review.

## Real held-out SciFact evaluation

Data: independently annotated SciFact corpus
([dataset](https://github.com/allenai/scifact), original SciFact DEV
`claims_dev.jsonl`). Its **gold rationale sentences are provided to the
model** as input premise, while the claim is used as hypothesis. Consequently,
this benchmark measures only classification conditional on an oracle-selected
evidence rationale, **not evidence retrieval or complete scientific
verification**. The model was *not* fine-tuned on SciFact. No DEV threshold
selection and no query-label leakage were used.

| Metric | Measured |
| --- | ---: |
| SciFact TRAIN gold rationale sets | 957 |
| SciFact DEV gold rationale sets | 338 |
| DEV SUPPORT / CONTRADICT | 216 / 122 |
| Provisional non-abstaining predictions | 132/338 (39.05% coverage) |
| Correct among predicted labels | 110/132 (83.33%) |
| 95% claim-cluster bootstrap selective accuracy | 75.65–90.24% |
| Correct over **all** gold rationales, abstentions counted as not correct | 110/338 (32.54%) |
| TRAIN-selected majority-label baseline, no abstention | 216/338 (63.91%) |
| Gold NEI / insufficient examples available | **None for this evaluation** |

**Interpretation:** The selective conditional figure is not full
classification accuracy. At fixed abstention thresholds, the NLI model
*does not beat the unconditional majority baseline* in coverage-weighted
correct labels. The 206 abstentions (including gold SUPPORT/CONTRADICT)
cannot be counted as correct `INSUFFICIENT` predictions. Claims that this
benchmark demonstrates reliable clinical fact-checking or superiority are
**unsupported**.

The machine-readable [independent results](../reports/evaluation/scifact_nli_dev.json)
include the label-by-prediction confusion table, model weight hash,
fixed thresholds, claim-cluster 500-bootstrap confidence intervals and
baseline counts. No licensed input paper text is stored in GitHub.

## Reproduction

Use [the pinned SciFact archive instructions](external_gold_evaluation.md)
and run the following after explicitly installing the optional NLI deps:

```bash
LITERATURE_EVIDENCE_NLI_DEVICE=cpu \
python -m scripts.evaluation.scifact_nli \
  --data /tmp/literature-gold/data \
  --model-dir /tmp/literature-nli-small \
  --output /tmp/scifact_nli_dev.json
```

The script checks SciFact input SHA-256 and model weights, and reports the
same aggregate protocol. Small floating-point variation across CPU/GPU,
PyTorch and Transformers versions can affect decisions near thresholds;
full CPU and GPU exact cross-environment parity remains unverified.

## Scientific limitations and next gates

This is an SNLI/MNLI-trained general-domain NLI model on SciFact expert
labels, not a scientific-domain-calibrated production classifier. It
cannot establish actual source authenticity, medical evidence quality,
effect direction, statistical significance, causality, publication bias,
RoB 2/ROBINS-I/GRADE or missing counterevidence. The neutral category
and low-confidence abstention are **not** validated as a true
insufficient-evidence class in this SciFact split. A separate,
independently adjudicated balanced **SUPPORT / REFUTE / NEI** dataset
and external clinical evaluation are mandatory before claiming robust
three-way factual reliability.
