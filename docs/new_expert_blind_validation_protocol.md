# Prospective biomedical expert-label blind validation — operational protocol

**Current status: PACKET-GENERATION SOFTWARE READY; NO NEW HUMAN GOLD
ANNOTATIONS COLLECTED; NO BLIND TEST OR SUPERIORITY COMPLETED.**

This document specifies a secure operational path for creating a *new*,
independently reviewed biomedical evaluation on **both** study retrieval
and SUPPORT/REFUTE/INSUFFICIENT reasoning. The user has approved preparing
the protocol; no independent biomedical sampling frame, expert panel,
adjudication criteria, sample size, primary success metric or statistical
decision rule has yet been approved. These scientific decisions are **not**
silently selected by this code.

## 1. Preregister before seeing any results

Record and sign off, independently of model/system builders:

- **Sampling/eligibility:** which clinical or nonclinical biomedical topics;
  claim/source inclusion and exclusion rules; date windows and document
  version, search queries, languages and reuse/contamination checks.
- **Ground truth:** what counts as an *eligible* relevant article versus
  judged nonrelevant; exact evidence quotation and source paragraph; whether
  SUPPORT/REFUTE/INSUFFICIENT is the appropriate task ontology. Separately
  record genuinely missing evidence versus an algorithm's refusal or lack of
  confidence. Retain **NULL, MIXED, BLOCKED, ERROR**, not as negatives.
- **Independent expert panel:** qualifications, conflicts of interest,
  independent judgments, and blinded allocation rules. Experts must actually
  evaluate the source content; the assistant or a model must **not**
  fabricate a ground-truth expert decision.
- **Primary outcome(s):** case-group unit, weighted or unweighted retrieval
  relevance, recall/precision only when gold coverage supports them; for NLI
  full-denominator accuracy and class-specific sensitivity with abstention
  coverage separately. Define loss weighting and confidence interval /
  statistical analysis *before* viewing outcomes.
- **Fair model execution:** exact named competitor commits/model hashes,
  data source access, matching evidence premises, fixed compute/network
  quota, clock window, failed-request handling, deterministic query sets.
  **Live provider discovery and NFCorpus fixed-corpus ranking are not
  interchangeable experiments.**
- **Leakage prevention:** document first-publication dates, benchmark
  ancestry, LLM/model pretraining contamination risk, no access to gold
  labels during prediction, frozen code hashes and independent custody.

Proposed decisions remain **OPEN**. Their approval is required before this
can be described as an independently blinded scientific validation.

## 2. Minimal independently collected candidate format

Obtain source documents under their actual legal terms. No patient-identifying
details, protected health data, private accounts, copyrighted full text
without permission, or secret clinical records should be included.

Candidate source file (JSON list, shown with **invented data only**):

```json
[
  {
    "candidate_id": "synthetic-001",
    "claim": "Simulated claim for software testing only.",
    "evidence": "Invented evidence paragraph. This is not a clinical finding.",
    "source_doi": "10.5555/synthetic",
    "source_locator": "synthetic-document:paragraph-1",
    "publication_type": "synthetic",
    "collection_date": "2026-10-19"
  }
]
```

`candidate_id`, `claim`, `evidence`, `source_doi` and
`source_locator` are required. Identifying provenance must be traceable,
but DOI syntax and a source locator alone **do not verify publication
authenticity**. The validator rejects answers, labels, model predictions,
unapproved fields, empty values, duplicates and oversized records.

For actual expert work, samples must be newly selected/collected according
to the approved prospective protocol. Old VitaminC/NFCorpus cases alone
do not make a new blinded holdout.

## 3. Prepare review packets without revealing model or gold labels

Run the deterministic, fully unit-tested
`scripts/evaluation/prepare_blinded_expert_packets.py` **locally within
an authorized secured environment**:

```sh
umask 077
export REVIEW_PACKET_SECRET_HEX="$(python -c 'import secrets;print(secrets.token_hex(32))')"
python -m scripts.evaluation.prepare_blinded_expert_packets \
  --input /dev/shm/approved-new-biomedical-candidates.json \
  --review-packet /dev/shm/reviewer-restricted/packet.jsonl \
  --private-map /dev/shm/custodian-restricted/blind-map.json \
  --manifest /dev/shm/custodian-restricted/packet-sha-manifest.json
unset REVIEW_PACKET_SECRET_HEX
```

- **Blinded packet:** claim, evidence, source details and an opaque HMAC
  `blind_id`, **without** original candidate IDs, classification results,
  model score columns, answer keys or gold labels.
- **Separate private mapping:** opaque IDs back to input IDs for a custodian
  only. It must never be distributed to labelers during the blind phase.
- **Integrity manifest:** SHA-256 of both files and explicit declarations
  `independent_expert_annotation_verified=false`,
  `blindness_verified=false`, and
  `classification_or_relevance_gold_generated=false`.
- All three files are exclusive-create, owner-readable/writeable (0600),
  with separate reviewer/private directories, and are **never committed
  to ordinary Git**. If an output write fails, any files produced by that
  call are cleaned up rather than left half-published.
- Opaque HMAC IDs hide original IDs but **cannot prevent experts from
  recognizing a study from its citation or wording**. This is
  *model-output/answer-blinded packet preparation*, not independently
  authenticated full blindness.

The CLI needs **actual independently sourced material and appropriately
authorized expert reviewers**. The repository contains only the source
validator, packet writer, tests and protocol, not real gold data.

## 4. Human reviewer and adjudication phase (NOT performed)

Qualified reviewers independently assess each assigned case, recording
the evidence quote's source location, retrieval relevance or evidence class,
explicit uncertainty, conflicts and reasons. A reviewer must not see the
system identity, model result, or another reviewer's label during the
independent stage, subject to the final approved blinding design.

A separate human adjudicator resolves disagreements under the preregistered
rule. **Never rewrite ambiguous, mixed, null or insufficient gold as
SUPPORT/REFUTE merely to increase accuracy.** Reviewer agreement must be
reported at the approved unit of analysis; if no independent judgments
exist, report `BLOCKED_MISSING_EXPERT_GOLD` rather than a perfect score.

After reviews are locked, the independent data custodian can freeze expert
labels and predictions in *separate* inaccessible-to-model input files,
capture SHA-256, and use the existing
`scripts.evaluation.dual_track_head_to_head` audit infrastructure to
score matched cases. Actual source-text provenance and reviewer integrity
are separate scientific checks, **not established by SHA alone**.

## 5. Status and release gate

| Requirement | Status |
|---|---|
| Operational label-free packet tool and synthetic tests | Implemented |
| Actual new biomedical source cohort | **NOT COLLECTED** |
| Independent authorized qualified expert panel | **NOT RECRUITED/VERIFIED** |
| Independently authored, prospective test gold | **NOT AVAILABLE** |
| Prespecified primary outcomes and analysis | **AWAITING SCIENTIFIC APPROVAL** |
| Model predictions frozen before gold is revealed | **NOT EXECUTED** |
| Expert agreement, adjudication, confidence intervals | **NOT EXECUTED** |
| Independent prospective scientific superiority | **NOT DEMONSTRATED** |

Any claimed result above the actual status would be scientifically
misleading. The code is not a substitute for independent experts, an ethics
review where applicable, or research-data rights. No npm Registry release.
