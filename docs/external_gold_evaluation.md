# Independent labeled science benchmarks — SciFact + EvidenceBench (2026-10-18)

**Result: external measurement completed, scientific superiority NOT established.**
The project audits literal quotes and provenance; it does *not* provide a
semantic scientific entailment classifier or hypothesis-to-evidence retriever.
An output marked TEXTUAL_MATCH_ONLY is never a SUPPORT classification.

## Independently sourced datasets and licensing

1. [SciFact (Wadden et al., EMNLP 2020)](https://github.com/allenai/scifact),
   official public train/dev labels. Data archive:
   https://scifact.s3-us-west-2.amazonaws.com/release/latest/data.tar.gz
   SHA-256: `11c621288d41ac144d29b13b0f8503b3820b7d6e8b1f6ff24dff335c196d76be`.
   Claims/evidence labels: **CC BY 4.0**. Corpus abstracts: **ODC-By 1.0**
   (Semantic Scholar S2ORC). The official test labels are *not* public, so
   SciFact **DEV**, not the hidden test set, was scored. No DEV tuning.
2. [EvidenceBench (Wang et al., COLM 2025)](https://github.com/EvidenceBench/EvidenceBench),
   official original TEST partition of 293 biomedical papers; source commit
   `bf1d9633c694381c7b016fd56ee9f95f48593cc3`, input SHA-256
   `771cc068e3e79764c2eb523e7d0d9fb276d00254a99212c73c1137674b49d18b`.
   Original TEST license: **CC BY**; original train/dev: **CC BY-NC-SA**.
   EvidenceBench uses large-scale *LLM-assisted labels with human expert
   validation*, not independent manual expert labels for every test instance.

No licensed article abstracts, input claims or annotations are copied into
this repository; only scripts, hashes, summary metrics and license attribution
are committed.

## SciFact: labeled cited-document evidence relevance proxy

Candidate set is the claim's **cited documents**, plus explicit annotated
evidence documents. Positives are cited candidate papers with an annotated
evidence rationale; negatives are cited papers without annotated rationales.
This is **not** open-corpus paper retrieval or SUPPORT/CONTRADICT classification.

* Train: 809 claims / 919 cited-document pairs; cutoffs fitted only on TRAIN.
* Dev: 300 claims / 339 cited-document pairs, **209 positive, 130 negative**.

| Candidate flagger | Dev precision | Dev recall | Dev F1 | Clustered bootstrap F1 95% |
|---|---:|---:|---:|---:|
| Existing MCP: use literal claim as supplied quote | undefined (no positive predictions) | 0.000 | **0.000** | 0.000–0.000 |
| Simple word coverage (train cutoff=0.38) | 0.699 | 0.909 | **0.790** | 0.748–0.830 |
| Jaccard (train cutoff=0.01) | 0.627 | 0.995 | 0.769 | 0.721–0.808 |

The quote auditor correctly finds **366/366** independently annotated gold
rationale sentences in their cited abstracts (case/whitespace changes
366/366), and **0/366** of the same quotes on unrelated source abstracts.
These are *extractive consistency and negative controls*, not tests that an
annotated rationale supports or contradicts a scientific claim. The cited
source sentences are provided from the gold dataset; they are **not autonomously
retrieved** by our MCP.

The product abstains on all evidence SUPPORTED vs CONTRADICTED labels;
semantic classification **coverage = 0%**, and selective classification
accuracy is **undefined** — not 100%, and not a competitor win.

## EvidenceBench original TEST: hypothesis-to-sentence evidence retrieval

* 293 test papers, with gold aspects linked to source sentences.
* Each ranker receives the same hypothesis and sentence candidate list.
* Macro recall is averaged over papers; 500 seeded paper-cluster bootstrap
  resamples provide an indicative 95% interval.
* Original EvidenceBench aspect recall is evaluated @10 and
  results-only aspect recall @5.
* Word overlap, Jaccard, first-k, deterministic random and third-party
  **rank-bm25 v0.2.2** are transparent baselines (not full competing
  scientific MCP products). The BM25 method was added **after exploratory
  results were inspected**; no preregistered confirmatory win is claimed.

| Method | Macro aspect recall@10 (95% bootstrap) |
|---|---:|
| Existing MCP hypothesis literal-match proxy | **0.000** (0.000–0.000) |
| Jaccard | 0.333 (0.303–0.366) |
| Word coverage | 0.420 (0.388–0.453) |
| Third-party rank-bm25 | 0.353 (0.323–0.387) |
| First 10 paper sentences | 0.495 (0.459–0.533) |
| Deterministic random 10 sentences | 0.221 (0.195–0.248) |
| Gold-derived oracle reference (**not a competitor**) | 1.000 (1.000–1.000) |

A separate sanity check located **1,348/1,348** gold-selected text sentences
in their supplied paper text. It does **not** infer hypothesis support,
medical validity, bias, causal inference, or semantic evidence quality.
The evidence selection baselines have genuine misses and false selections.

## Reproduction: pinned, fail-closed

```bash
python -m pip install -e .
python -m pip install -r scripts/evaluation/requirements.txt
mkdir -p /tmp/literature-gold
curl -fsSL https://scifact.s3-us-west-2.amazonaws.com/release/latest/data.tar.gz -o /tmp/literature-gold/scifact.tar.gz
echo '11c621288d41ac144d29b13b0f8503b3820b7d6e8b1f6ff24dff335c196d76be  /tmp/literature-gold/scifact.tar.gz' | sha256sum -c -
tar -xzf /tmp/literature-gold/scifact.tar.gz -C /tmp/literature-gold/
curl -fsSL https://raw.githubusercontent.com/EvidenceBench/EvidenceBench/bf1d9633c694381c7b016fd56ee9f95f48593cc3/datasets/evidencebench_test_set.json -o /tmp/literature-gold/evidencebench_test.json
echo '771cc068e3e79764c2eb523e7d0d9fb276d00254a99212c73c1137674b49d18b  /tmp/literature-gold/evidencebench_test.json' | sha256sum -c -
python -m scripts.evaluation.scifact_gold --data /tmp/literature-gold/data --output /tmp/scifact_dev.json
python -m scripts.evaluation.evidencebench_gold --data /tmp/literature-gold/evidencebench_test.json --output /tmp/evidencebench_test.json
diff -u reports/evaluation/scifact_dev.json /tmp/scifact_dev.json
diff -u reports/evaluation/evidencebench_test.json /tmp/evidencebench_test.json
```

CI executes these instructions in a dedicated external-gold job, alongside
the original **100% Python statement and branch gate**, TypeScript and native
tests. Exact report reproduction is required and the data hash must match.
No downloads or derived artifacts are published to npm.

## What is NOT proven

* **No superiority over commercial tools, published SciFact systems,
  MultiVerS, GPT-4, Claude, Elicit or Cochrane reviewers** was measured.
* No blinded expert-gold RoB2, ROBINS-I V2, GRADE or full PRISMA outcome
  accuracy, and no expert clinical inter-rater calibration.
* No real 9+/10 scientific accuracy score; the current tool has **no semantic
  fact-checker and no *automatically operated*, source-verified evidence ranker**. A later opt-in user-supplied BM25 candidate ranker does not verify semantic claims.
* A model for clinical-grade scientific correctness would require an
  explicitly designed and independently tested semantic verification stage.
  This benchmark does not silently insert a new model or claim a validated
  improvement.

Full machine-readable metrics: [SciFact](../reports/evaluation/scifact_dev.json)
and [EvidenceBench](../reports/evaluation/evidencebench_test.json).
