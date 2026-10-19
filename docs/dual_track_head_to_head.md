# Dual-track independent benchmark: retrieval and evidence decisions

**Status: EVALUATION HARNESS READY — NO INDEPENDENT COMPETITOR RESULT YET.**

The research comparison has two distinct, equal-status tracks:
**(A) literature discovery** and **(B) evidence verdict classification**.
No composite score, primary metric, statistical superiority or clinical
utility claim is selected or inferred.

## Why this is necessary

Earlier three-query competitor smokes measured retrieval *counts and latency*,
not expert-judged paper relevance. Existing SciFact open-corpus experiments
assessed baseline lexical ranking using incompletely labeled gold, and
HealthVer/HealthFC/SciFact model tests were explored retrospectively. Neither
constitutes a blind, same-query, same-document **competitor-versus-ours
independent** evaluation. All existing evidence, NULL/MIXED/BLOCKED and
negative findings remain unchanged.

## Strict sealed external inputs

Place externally authorized, *independently sourced* gold cases and **real
outputs executed on exactly those cases** outside Git history. Three JSON files
are required:

- `gold.json`: two arrays, `retrieval` and `classification`.
  Every retrieval row has `id` and a `known_positive_ids` list. An empty
  list is allowed but remains **unscored**, not a negative result.
  Every classification row has `id` and an independent expert
  `label` of `SUPPORT`, `REFUTE` or `INSUFFICIENT`.
- `outputs.json`: mapping from **at least two actual systems** to objects
  each containing the same `retrieval` and `classification` case IDs.
  Retrieval rows: `id`, `status` (`OK`, `PARTIAL`, `NULL`, `BLOCKED`,
  `ERROR`) and ordered `ranked_ids`. Classification rows: `id` and
  `prediction`: a gold class, or `ABSTAIN`, `NULL`, `MIXED`, `BLOCKED`, `ERROR`.
  No system may omit difficult cases. `NULL`/`BLOCKED`/`ERROR` searches must
  have **empty** results, not pretend to succeed.
- `manifest.json`: immutable externally pre-registered SHA-256 values for
  **both** JSON files, plus nonempty `dataset_reference` and
  `evaluation_reference` (short identifying strings). SHA verifies local
  bytes only; it does **not independently authenticate origin or blinding**.

Minimal illustrative **synthetic** format (not a scientific dataset):

```jsonc
// gold.json
{
  "retrieval": [{"id": "q1", "known_positive_ids": ["paper_A"]}],
  "classification": [{"id": "v1", "label": "SUPPORT"}]
}
```

```jsonc
// outputs.json
{
  "own": {
    "retrieval": [{"id": "q1", "status": "OK", "ranked_ids": ["paper_A"]}],
    "classification": [{"id": "v1", "prediction": "ABSTAIN"}]
  },
  "competitor": {
    "retrieval": [{"id": "q1", "status": "PARTIAL", "ranked_ids": []}],
    "classification": [{"id": "v1", "prediction": "SUPPORT"}]
  }
}
```

```jsonc
// manifest.json (hashes must be computed from real files and frozen before running)
{
  "gold_sha256": "<64 lowercase hex characters>",
  "outputs_sha256": "<64 lowercase hex characters>",
  "dataset_reference": "source, edition, split, license",
  "evaluation_reference": "comparison run reference; date; frozen settings"
}
```

## Executing without leaking cases

```sh
python -m scripts.evaluation.dual_track_head_to_head \
  --manifest /tmp/manifest.json \
  --gold /tmp/gold.json \
  --outputs /tmp/outputs.json \
  --report /tmp/two-track-aggregates.json
```

The report contains **only aggregate class confusions, counts, diagnostic
metrics, explicit limitations, checksum references, and descriptive paired
deltas**. It never exports claim text, ranked document IDs, gold item IDs,
model probability arrays, or patient records.

**Literature search:** known-positive recall at 1/5/10 and first known-positive
MRR. No precision, specificity or false-positive rate can be inferred when
full-corpus relevance judgments are unavailable. Every no-gold, blocked,
failed and partial query is counted. The denominator is explicit.

**Evidence classification:** full fixed-denominator accuracy, macro-F1,
per-class recall/F1, selective accuracy and decision coverage; ABSTAIN, NULL,
MIXED, BLOCKED, ERROR are separate non-decisions and never relabeled
NEUTRAL/INSUFFICIENT or silently excluded from all-case accuracy.

Paired deltas compare exactly matched case IDs, **not** statistical
significance. The report intentionally leaves `primary_metric_selected=false`,
`independent_gold_provenance_verified=false`,
`blinded_evaluation_verified=false` and
`competitor_executions_verified=false`.

## Public exploratory runs (not blind independent comparisons)

A controlled public NFCorpus fixed-corpus BM25 baseline is recorded at
[the two-dataset report](two_public_dataset_exploratory.md). It reports
known-positive Recall@1/5/10 and MRR@10 without misclassifying unjudged
results as negatives. Three **historically pinned** NLI models are also
evaluated against the complete public VitaminC 55,197-pair test with
unchanged confidence/margin rules. These are separate exploratory tasks,
**not** the independent blinded same-task competitor protocol outlined above.

## Confirmed candidate sources (not executed)

See [candidate audit](dual_track_candidate_sources.md): official BEIR
NFCorpus retrieval archive and pinned VitaminC test file have passed
byte-level checks. Their published retrospective labels are intentionally
not opened here. NFCorpus requires a fixed-corpus ranking comparator;
VitaminC is a Wikipedia, not biomedical, evidence-label benchmark.
These **do not constitute a blinded head-to-head study**.

## Required scientific steps before any superiority claim

1. Select the **independent labeled dataset(s)**, make licensing and
   provenance available and fix the gold/data leakage exclusion protocol.
2. Identify exactly which **competing implementations and revisions**
   will be executed; hold retrieval sources, cutoffs, time budgets and
   NLI evidence premises fixed or state unavoidable scope differences.
3. Specify the **primary metric(s)**, any error costs and statistical
   comparison method *before inspecting test answers*. User approval is
   required to make these scientific design decisions.
4. Preserve the predictions, raw and transformed data in permitted secure
   storage outside normal Git history; pre-register immutable hashes.
5. Run real systems blind to gold labels when feasible and have an
   independent judge verify blinding and relevance/verdict label quality.
6. Only then consider preregistered confidence intervals and a conditional
   scientific claim. If no valid matched gold exists, report **BLOCKED**,
   never a win.

No npm Registry publication or default NLI engine change is required.

## Reproduction checks

```sh
pytest -q tests/test_dual_track_audit.py
pytest -q --cov=literature_evidence_mcp --cov-branch --cov-fail-under=100
```

The tests use **synthetic cases only**, including mismatched query/case IDs,
duplicate inputs, incomplete annotations, incorrect statuses, empty gold,
non-decisions, failed competitor results, SHA tampering and report non-leakage.
