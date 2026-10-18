# Independent HealthVer three-class test of the experimental NLI tool

**Verdict: limited, experimentally measured; not a reliable scientific
fact-checker.** The optional `nli_assess_evidence` remains disabled unless
the user explicitly installs and configures its pinned local model.

## Source and precommitted, unchanged decision rule

- Independent dataset: **HealthVer**, Sarrouti et al., *Evidence-based
  Fact-Checking of Health-related Claims*, Findings of EMNLP 2021.
  Official paper: https://aclanthology.org/2021.findings-emnlp.297/
  Official data: https://github.com/sarrouti/HealthVer.
- Dataset frozen at upstream commit
  `b20ac99ceed62f5264a319fa25a854df1668d85b`.
  CSV SHA-256:
  `train=57668949f79d0f46e66d74df4b0bc9812cad4d5ad7c5dd03dfba008a608b3f2a`,
  `dev=6f8ea31cbcf2ea5a2d3c82d65587d66e96de4f70e72642bbf7f61fec6ef8a93a`,
  `test=cf457d2dcddd7a736408082d0037527884f7ca3bda06729e1da5ec9e3b135819`.
- The upstream data repository has **no explicit LICENSE file**. Raw
  annotations and evidence texts are **not republished** in our repository;
  this project stores only aggregate results and SHA-256 values. Consult
  the original publishers before redistribution.
- We used the **already pinned** SNLI/MNLI-trained
  `cross-encoder/nli-deberta-v3-small` (revision
  `fa2804872c3b4bd748f38c0185cc85775361e735`; weights SHA-256
  `ebc79588dd73ccfb6a3f6078519cfbf512c5305384c5ea1845bc71cd32216e86`).
  We did not train it on HealthVer, and did **not** use train/dev/test
  labels to tune the pretrained model or its existing `0.70` confidence
  and `0.15` winning-label margin thresholds. The comparator majority
  label was selected from HealthVer TRAIN **only**.

## What was tested

The existing NLI algorithm received **an already supplied evidence statement**
and the matching claim; it classified the relation. This is **not an
end-to-end search/retrieval, clinical-fact verification or causal conclusion**.

| Property | Observed |
| --- | ---: |
| Original train / dev / test rows | 10,590 / 1,917 / 1,823 |
| Original TEST SUPPORTS | 671 |
| Original TEST REFUTES | 425 |
| Original TEST NEUTRAL | 727 |
| Unique TEST claim–evidence pairs | 1,694 |
| Identical repeated TEST rows | 129 |
| Exact claim overlap between TRAIN and TEST | 1 unique claim |
| **Three-class test accuracy** | **46.57%** |
| **Three-class macro-F1** | **38.42%** |
| Balanced accuracy | 43.89% |
| **NEUTRAL F1** | **58.83%** |
| NEUTRAL recall | 89.13% |
| SUPPORT recall | 8.20% |
| REFUTE recall | 34.35% |
| Explicit SUPPORT/REFUTE decision coverage | 19.03% |
| Accuracy conditional on an explicit SUPPORT/REFUTE prediction | 57.93% |
| TRAIN majority-label baseline accuracy on TEST | 39.88% |
| TRAIN majority-label baseline macro-F1 on TEST | 19.01% |
| Deduplicated TEST accuracy (1,694 unique pairs) | **43.09%** |
| Deduplicated TEST macro-F1 | **37.05%** |

### Uncertainty (claim-cluster bootstrap, 500 seeded resamples)

| Metric | 95% percentile interval |
| --- | ---: |
| Overall test accuracy | 41.40–52.70% |
| Macro-F1 | 34.50–42.32% |
| Balanced accuracy | 41.21–46.85% |

The bootstrap cluster unit is an entire **claim**, rather than assuming
repeated claim–evidence pairs are statistically independent. These are
descriptive uncertainty intervals, not evidence of superiority or
clinical validation. Label frequencies are not balanced in TEST.

### Three-way confusion (gold rows × predicted columns)

| True label | Pred SUPPORT | Pred REFUTE | Pred NEUTRAL |
| --- | ---: | ---: | ---: |
| SUPPORT | 55 | 61 | 555 |
| REFUTE | 6 | 146 | 273 |
| NEUTRAL | 9 | 70 | 648 |

Crucial limitation: the NLI tool emits
`INSUFFICIENT_MODEL_EVIDENCE` for **both** a neutral model score
and an unconfident ranking. Both were mapped to HealthVer `NEUTRAL`
for this *external* three-class assessment. Thus the model's high NEUTRAL
recall is partially driven by **abstention on genuinely supporting
or refuting examples**. Its SUPPORT recall of 8.20% is particularly
weak. `INSUFFICIENT_MODEL_EVIDENCE` is not an established medical
"not enough evidence" verdict.

HealthVer was originally manually annotated in the COVID-19 subject
domain. Its authors describe some inter-annotator checking, but it is
**not an independently blinded clinician safety certification**.
The upstream split contains repeated pairs and an overlapping claim
between TRAIN and TEST; no HealthVer data was used for our model
training. The duplicate-free sensitivity analysis shows that
repeats can inflate headline accuracy.

## Diagnostic extension: why support fails

The same fixed NLI weights and frozen threshold/margin were re-run on the
same exact HealthVer TEST snapshot. **No retraining, threshold tuning,
new scientific axiom or change to the production MCP verdicts.** We
inspected the three model softmax scores *before* the existing
neutral/low-confidence paths are combined into
`INSUFFICIENT_MODEL_EVIDENCE`.

| Production decision origin | TEST cases | Actual SUPPORT | Actual REFUTE | Actual NEUTRAL |
| --- | ---: | ---: | ---: | ---: |
| Model's raw top class is NEUTRAL | **1,447** | **540** | **269** | 638 |
| Directional score below 0.70 threshold | 29 | 15 | 4 | 10 |
| Model emitted SUPPORT or REFUTE | 347 | 116 | 152 | 79 |
| Directional margin below 0.15 | 0 | 0 | 0 | 0 |

This is a critical difference: the **809 wrong gold SUPPORT/REFUTE
examples with raw NEUTRAL argmax** were not simply rejected by the
confidence threshold; the model *ranked* NEUTRAL above both directional
labels. Lowering a threshold cannot by itself fix these rankings, and
we have **not** changed that threshold.

The 0.15 winning-label margin is mathematically redundant here:
if a class has a probability of at least 0.70, the runner-up can be no
higher than 0.30, so the winning margin is at least 0.40 > 0.15.
This statement describes the **frozen configuration**, not a proposal to
automatically change the classifier.

Without mixing abstentions into NEUTRAL, the raw argmax NLI model
achieved **46.85% three-way accuracy** and **39.30% macro-F1**,
compared with 46.57% and 38.42% under the published frozen
production mapping. This small difference does **not** establish that
unthresholded results are reliable.

The uncalibrated raw three-class model's 10-bin **expected calibration
error (ECE) is 0.4932**, and its three-class Brier score is **1.0119**.
These *descriptive held-out HealthVer estimates* are especially poor on
this out-of-training-domain dataset and must not be used as calibrated
probabilities that medical claims are true. Model calibration,
threshold selection and independent confirmation would require a
separate, explicitly authorized scientific design.

The data include original topic identifiers. We report exploratory
topic-stratified results only for groups with **at least 30 TEST
rows** (19 reportable topics, 36 smaller topic groups suppressed).
These are not pre-registered superiority tests and were not used
to tune parameters. Separately, excluding the exact training-overlap
claim leaves **1,817 TEST rows**, with **46.51% accuracy**.
The model was never trained on HealthVer, so this is a sensitivity
rather than a leakage correction.

Full counts, raw argmax three-way confusion, ten calibration bins,
topic-level aggregated metrics and label provenance are committed
in [the machine-readable report](../reports/evaluation/healthver_test.json).
The original third-party raw claim/evidence texts are not committed.

## Baseline and comparison boundaries

The frozen model beat the simple *unconditional majority-label* comparator
on this test by 6.69 percentage points in overall accuracy, but 46.57%
accuracy is **not acceptable as a reliable scientific fact-checker**.
We have not compared under matched conditions with a modern, scientifically
fine-tuned commercial or research fact-checker. The HealthVer paper's
original leaderboard systems were **trained on HealthVer**; quoting
their scores as if they were zero-shot head-to-head results is invalid.

The previous [SciFact DEV experiment](nli_scientific_validation.md)
measured 83.33% accuracy **conditional on only 39.05% decision coverage**
over 338 gold rationale sets; it did not include an independent
NEUTRAL class. These are *different datasets, protocols and endpoints*
and do not prove generalization or meaningful clinical reliability.

## Reproduction without republishing third-party text

```bash
python -m pip install -e '.[nli]'
mkdir -p /tmp/healthver-gold
rev=b20ac99ceed62f5264a319fa25a854df1668d85b
for split in train dev test; do
  curl -fsSL "https://raw.githubusercontent.com/sarrouti/HealthVer/$rev/data/healthver_$split.csv" \
    -o "/tmp/healthver-gold/healthver_$split.csv"
done
# scripts/evaluation/healthver_nli.py verifies all three CSV SHA-256 hashes
# and the explicitly configured pinned offline safetensors model.
python -m scripts.evaluation.healthver_nli \
  --data /tmp/healthver-gold \
  --model-dir /tmp/literature-nli-small \
  --output /tmp/healthver_test.json
```

`/tmp/literature-nli-small` is a separately downloaded pinned model as
documented in [the experimental NLI setup](nli_scientific_validation.md).
A dedicated optional GitHub Actions
`healthver-gold-audit.yml` workflow can rerun the complete CPU benchmark;
CI also checks mathematical invariants and source/metric metadata without
making a 542 MB NLI model a default install dependency.

Read the full [machine-readable metrics](../reports/evaluation/healthver_test.json),
including all confusion counts, deduplicated sensitivity, majority baseline,
and source/model SHA-256 identifiers.

## Mandatory remaining evidence

Accurate evidence *retrieval*, medical source authentication,
clinically meaningful "insufficient evidence" vs *mere model uncertainty*,
prospective clinician adjudication, calibration, and controlled benchmarking
against scientific-domain classifiers are all **unresolved**.
No score of 9+/10 or scientifically validated accuracy is asserted.
