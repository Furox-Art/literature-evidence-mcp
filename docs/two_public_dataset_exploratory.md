# Two public-dataset exploratory evaluations (2026-10-19)

**EXPLORATORY — retrospective publicly available test sets; no scientific superiority or prospective blinding claim.**

This report is intentionally split into two incomparable tasks. Neither a
composite score nor a new post-hoc primary scientific success criterion is
introduced. No production model or literature-provider method was modified.

## A. NFCorpus — fixed-corpus biomedical retrieval

The BEIR NFCorpus archive SHA-256
`efe5be03f8c5b86a5870102d0599d227c8c6e2484328e68c6522560385671b0b`
was reverified, and **323 test queries**, **3,633 fixed scientific documents**
and **12,334 labeled document-query relevance pairs** were parsed. Original
licensed documents, queries and judgments stayed in WSL memory.

The project’s existing `rank_supplied_evidence` mechanism uses
`rank-bm25 0.2.2 BM25Okapi`, lowercase word tokenization
(two or more characters), exact query-term overlap filtering, and
deterministic score/doc-ID tie ordering. This benchmark reuses the
*same ranking algorithm*, but builds the corpus index once so all 323
queries share exactly the same fixed document collection. No embeddings,
reranker, live API, tuning, fit, or external competitor was introduced.

| Diagnostic | Value |
|---|---:|
| Known-positive Recall@1 | 5.69% |
| Known-positive Recall@5 | 11.20% |
| Known-positive Recall@10 | 14.49% |
| MRR@10 for first known positive | 0.512 |
| Queries with no lexical term overlap | 25 / 323 |

These are **different metrics**: recall averages the fraction of all *known
positive* papers retrieved for each query, while MRR rewards how early the
*first* matching paper occurs. Graded relevance judgments were reduced to
`score>0` solely for this established known-positive recall diagnostic.
Unjudged documents were **not** called irrelevant. Corpus precision and
false-positive rates remain **undefined**.

**Scope limit:** NFCorpus evaluates offline ranking over 3,633 documents,
not whether OpenAlex, Crossref, Europe PMC or Semantic Scholar APIs find
missing studies in the current literature. It cannot establish broader
science-search completeness or a win over Elicit, Consensus or other MCPs.

### Auditable report

`reports/evaluation/nfcorpus_fixed_bm25_exploratory.json` contains aggregate
measurements; see its method settings and explicit limitations.
Technical runner: `scripts/evaluation/nfcorpus_fixed_bm25_exploratory.py`.

## B. VitaminC — public cross-domain claim–evidence reasoning

The pinned VitaminC test file is a retrospective, openly published Wikipedia
revision-derived set, **55,197 pairs**. Source SHA-256:
`7ad1808dbc30c62e0a1427a53022d0dfaff668a1fde3c4b612a2d266edd753ad`.

The source labels are **27,664 SUPPORTS**, **20,265 REFUTES**, and
**7,268 NOT ENOUGH INFO**. The experiment uses the same three **previously
pinned** DeBERTa NLI checkpoints, unchanged tokenizer and model revisions,
and unchanged 0.70 confidence / 0.15 directional margin. No additional
training, tuning, post-hoc threshold search, or default-engine change.

Crucial gold-label caveat: original `NOT ENOUGH INFO` is mapped to the
model’s NLI `NEUTRAL` as an **exploratory proxy**. The model’s
`INSUFFICIENT_MODEL_EVIDENCE` output can also be an *abstention* rather
than NLI semantic neutral. Therefore reported classification accuracy
must **not** be interpreted as accurate clinical scientific evidence
sufficiency. The two concepts are not validated as equivalent.

## Full frozen VitaminC CPU/GPU evaluation — aggregate metrics

Each of the following checkpoints was independently verified by its fixed SHA-256
and evaluated across all **55,197** public test pairs (real edits 34,481;
synthetic revisions 20,716) on CUDA. There are **16,487** distinct case IDs;
**537** additional matching claim/evidence pairs after casefolding and
trimming leading/trailing whitespace. No examples were silently dropped.

| Previously pinned model | Accuracy | Macro-F1 | SUPPORT recall | REFUTE recall | NEUTRAL recall | Non-neutral decision coverage |
|---|---:|---:|---:|---:|---:|---:|
| Original DeBERTa-small | 54.69% | 52.95% | 49.10% | 57.88% | 67.06% | 58.40% |
| FEVER/ANLI DeBERTa-base | 60.18% | 57.59% | 66.46% | 41.95% | 87.15% | 53.66% |
| General DeBERTa-base | 58.20% | 56.21% | 54.34% | 59.26% | 69.92% | 59.03% |

**Mixed finding, not a uniform win:** The FEVER/ANLI model has the highest
retrospective overall accuracy (60.18% versus 54.69% for the default small
model) and macro-F1 (57.59% versus 52.95%). **Its REFUTE recall is worse**:
41.95% versus 57.88% for the original (about **−15.93 percentage points**).
The general-base model's REFUTE recall is 59.26%. Do not suppress this
negative finding or promote a new default on these data.

`NOT ENOUGH INFO` is the source class, **not** verified clinical
insufficiency; mapping it to NLI `NEUTRAL` and folding low-confidence
abstentions into the same output is a limitation of the unchanged historical
scoring rule. *Non-neutral decision coverage* is distinct from correctness;
`selective.accuracy_given_non_neutral_prediction` is additionally reported
in the machine-readable aggregates with its own denominator.

Machine-readable, aggregate-only results:

- `reports/evaluation/vitaminc_frozen_original_deberta_small_exploratory.json`
- `reports/evaluation/vitaminc_fever_anli_deberta_base_exploratory.json`
- `reports/evaluation/vitaminc_general_deberta_base_exploratory.json`

These files include confusion tables, per-class recall, unique-pair
sensitivity, Brier diagnostics and published source/model SHA checks. They
include **no original source claim or evidence text and no per-example IDs or
prediction vectors**. No significance test, calibrated clinical probability,
independent blinded test, model promotion, or competitor-MCP comparison was
performed.


The runner keeps claim, evidence, IDs and per-case predictions in volatile
computation only. Public output is aggregate confusion, accuracy, macro-F1,
class recall, decision coverage, exact-duplicate sensitivity and checksum
identifiers. No original or transformed licensed text is committed.

Technical runner:
`scripts/evaluation/vitaminc_three_pinned_exploratory.py`.

## Scientific interpretation and limits

- These **public retrospective** data may appear in training/pretraining or
  prior model selection. Fresh blind scientific confirmation remains absent.
- There was **no same-task competitor execution** (e.g. other MCP servers);
  the NFCorpus track assessed one existing fixed-corpus BM25 engine and the
  VitaminC track compared existing pinned NLI weights. Do not call this a
  verified head-to-head win or production-model promotion.
- VitaminC is **not a biomedical clinical reliability dataset**. Clinical
  claims, causality, systematic review quality, completeness and human
  accuracy remain unproven.
- Negative, NULL, MIXED, BLOCKED and insufficient-evidence states must be
  retained; technical coverage %100 is not a scientific-validity score.
- These tasks remain distinct. **Do not average retrieval recall with NLI
  accuracy into a single science performance metric**.

No npm Registry publication.
