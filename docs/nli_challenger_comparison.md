# Exploratory NLI challenger comparison

**Scientific status: experimental, NOT validated clinical fact checking.** Two pinned,
externally trained checkpoints were assessed alongside the existing DeBERTa-small
under the **same unchanged decision rule**: directional softmax >= 0.70 and
winning margin >= 0.15. The user-selected 35th MCP tool makes candidates
available **only after explicit local configuration**. The original NLI
tool and other 34 MCP tools retain their behavior. No npm registry release.

## Models, provenance and pinning

| Reference | Model name | Immutable Hugging Face revision | License |
|---|---|---|---|
| Existing reference only | cross-encoder/nli-deberta-v3-small | fa2804872c3b4bd748f38c0185cc85775361e735 | Apache-2.0 |
| `fever_anli_deberta_base` | MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli | 6f5cf0a2b59cabb106aca4c287eed12e357e90eb | MIT |
| `general_deberta_base` | cross-encoder/nli-deberta-v3-base | 6c749ce3425cd33b46d187e45b92bbf96ee12ec7 | Apache-2.0 |

Model weight SHA-256: original
ebc79588dd73ccfb6a3f6078519cfbf512c5305384c5ea1845bc71cd32216e86;
FEVER/ANLI challenger
06d6fd89edd4f97816831626daafbdb0b029cf63bae8edc0bccab1d64e2e7707;
general DeBERTa challenger
d8148c6d49e0a7925134294c56326c71fe0ab1dc390e37355e00c7efbb488afa.

The challenger MCP implementation also checks pinned tokenizer and config
files by SHA-256, enforces a three-class label mapping, uses offline
safetensors with remote code disabled, and never downloads checkpoints
implicitly. Third-party training descriptions come from model cards, not a
full independently audited training history.

## Frozen-model independent benchmarks

### HealthVer: 1,823 labeled TEST rows, 1,694 distinct evidence pairs

| Model | Accuracy | Three-class macro-F1 | SUPPORT recall | Deduplicated accuracy |
|---|---:|---:|---:|---:|
| Existing DeBERTa-small | 46.57% | 38.42% | 8.20% | 43.09% |
| FEVER/ANLI DeBERTa-base | **48.99%** | **41.67%** | **14.01%** | **45.51%** |
| General DeBERTa-base | 46.85% | 38.28% | 7.90% | 43.27% |

The FEVER/ANLI candidate improved accuracy relative to the original by
**+2.41 percentage points**. A claim-cluster paired bootstrap (500 seeded
resamples) returned an exploratory 95% interval of **+0.22 to +4.69 pp**.
The general-base candidate improved accuracy by +0.27 pp, with a paired
interval of **-1.74 to +2.26 pp**.

**Important:** SUPPORT recall remains only 14.01% for the stronger
HealthVer candidate. Neither model is suitable for unreviewed medical
or scientific verification. The benchmark includes repeated pairs, so
deduplicated sensitivity is shown explicitly.

### SciFact: 338 expert-labeled oracle evidence rationale sets

| Model | Decision coverage | Accuracy given directional prediction | Correct out of ALL 338 |
|---|---:|---:|---:|
| Existing DeBERTa-small | 39.05% (132 decisions) | 83.33% (110/132) | 32.54% (110/338) |
| FEVER/ANLI DeBERTa-base | 45.27% (153 decisions) | 91.50% (140/153) | 41.42% (140/338) |
| General DeBERTa-base | 47.04% (159 decisions) | 91.19% (145/159) | 42.90% (145/338) |

SciFact rationales were **given** to the classifier as premises; evidence
selection and source authentication were not evaluated. This annotated
subset has **no independent NEUTRAL gold category**. Unanswered evidence
is not counted as a correct NEUTRAL classification.

### Fundamental scientific limitation

The HealthVer TEST and SciFact DEV data were **already inspected in previous
experiments**. These head-to-head comparisons are strictly exploratory.
Selecting a winning production model from these results would cause
post-selection bias; no head-to-head result here is prospective,
blinded confirmation. Neither model has been promoted as the default.

Both systems are pretrained third-party architectures: this project
did **not** design or train a new architecture. Reliability, calibration,
unobserved counterevidence, retrieval, study-quality biases, causal
conclusions, and real medical evidence insufficiency remain unresolved.

## Explicit experimental MCP use

Install the existing optional local NLI dependencies:

    python -m pip install -e '.[nli]'

Download each checkpoint from its exact revision listed above into
a local directory using the Hugging Face snapshot_download API, requesting
only *.safetensors, *.json, *.model and *.txt files. The runtime
enforces all recorded file hashes; altered or missing files fail closed.

    export LITERATURE_EVIDENCE_NLI_FEVER_MODEL_DIR=/tmp/fever-model
    export LITERATURE_EVIDENCE_NLI_GENERAL_MODEL_DIR=/tmp/general-model

Call the **`nli_assess_challenger_evidence`** MCP tool with parameters
**claim**, **evidence**, **source_id**, and mandatory **candidate**:
choose either **`fever_anli_deberta_base`** or **`general_deberta_base`**.
A model-specific directory is required; missing configuration returns
`EXPERIMENTAL_MODEL_NOT_CONFIGURED`, not a fabricated verdict.
No automatic model selection or network inference is performed.

Reproducible evaluation entry points:

- `scripts/evaluation/nli_challenger_benchmark.py` — HealthVer TEST
- `scripts/evaluation/nli_scifact_challengers.py` — SciFact DEV
- `reports/evaluation/healthver_nli_paired_challengers.json`
- `reports/evaluation/scifact_nli_paired_challengers.json`

Original third-party data and large model files are **not committed**.
See the main HealthVer and SciFact methodology documents for pinned
dataset SHA-256 hashes, licenses and data retrieval steps.

**Next gate:** independently expert-annotated, previously unseen balanced
SUPPORT/REFUTE/INSUFFICIENT cases and prospective calibrated validation
must be completed before any production promotion or 9+/10 scientific claim.
