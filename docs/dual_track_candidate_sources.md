# Candidate datasets for two-track independent evaluation

**State on 2026-10-19: SOURCE BYTES VERIFIED; NO BLIND TEST EXECUTED.**
This is an evidence provenance check and candidate selection, not a
competitor benchmark, publication-grade preregistration, or a scientific win.

## Track A: biomedical document retrieval — BEIR NFCorpus

- Upstream benchmark: [BEIR official repository](https://github.com/beir-cellar/beir)
  and its NFCorpus release.
- Exact archive: [nfcorpus.zip](https://public.ukp.informatik.tu-darmstadt.de/thakur/BEIR/datasets/nfcorpus.zip)
- Official BEIR archive MD5:
  `a89dba18a62ef92f7d323ec890a0d38d`
- Locally verified SHA-256:
  `efe5be03f8c5b86a5870102d0599d227c8c6e2484328e68c6522560385671b0b`
- Original structure confirmed **without inspecting labels or queries**:
  `corpus.jsonl`, `queries.jsonl`, and
  `qrels/train.tsv`, `qrels/dev.tsv`, `qrels/test.tsv`.
- Published BEIR statistics: 3,633 documents, 323 test queries,
  12,334 test qrels (some judgments are graded).
- Source mirror metadata indicates CC BY-SA 4.0. Observe original
  publication permissions; **do not commit corpus or gold to Git**.

**Critical applicability restriction:** This is a **fixed 3,633-document
ranking** benchmark. Existing live Crossref/OpenAlex/Europe PMC/Semantic
Scholar API discovery cannot be compared fairly on NFCorpus document IDs
without a fixed-corpus retrieval adapter shared by every competitor.
A query against live academic APIs is **not** an NFCorpus run.

**Gold caveat:** The test labels are old and public. Check prior model
training and similar-query overlap; they are not inherently
previously unseen or prospectively blinded just because this session
has not opened the labels.

## Track B: three-class claim-evidence reasoning — VitaminC

- [Original authors' repo and data license](https://github.com/TalSchuster/VitaminC)
  and [Hugging Face dataset](https://huggingface.co/datasets/tals/vitaminc).
- Pinned repository revision:
  `be6febb761b0b2807687e61e0b5282e459df2fa0`
- Pinned artifact: `test.jsonl`, 28,717,099 bytes, 55,197 nonblank lines.
- SHA-256:
  `7ad1808dbc30c62e0a1427a53022d0dfaff668a1fde3c4b612a2d266edd753ad`
- The dataset contains claim-evidence pairs with **SUPPORTS, REFUTES,
  NOT ENOUGH INFO**; source terms: CC BY-SA 3.0 and Wikipedia
  page-specific terms. It also includes both real and synthetic revisions.
- Frozen test file was fetched into private WSL RAM and **not parsed for
  gold labels, claim text, or evidence**. Original test data not uploaded.

**Critical applicability restriction:** VitaminC is based on **Wikipedia
article edits**, not clinician-graded biomedical claims. A result on
VitaminC can be a cross-domain semantic fact-checking stress test;
**it cannot establish clinical scientific evidence reliability**.
Wikipedia revisions may also produce multiple related cases: keep
`case_id` groups together for any future bootstrap or split checks.
Any mapping between VitaminC labels and the MCP's ABSTAIN, NULL,
MIXED/BLOCKED states needs to be frozen before viewing test results.

**Independence caveat:** Public VitaminC may have entered pretraining
or model selection elsewhere. No public retrospective test can by
itself substantiate prospective blinded independence.

## Alternatives not silently substituted

- **BioASQ 2026 Task 14b** is directly biomedical and supplies article-level
  questions and gold documents, but downloading gold requires challenge
  registration, and 2026 test labels have been released publicly.
- **Check-COVID** supplies scientific-paper evidence for COVID claims, but
  uses source-specific annotations and class/subset definitions. It
  cannot be mapped to a three-class primary test without a separately
  approved mapping.
- **FEVEROUS** is a three-class structured/unstructured Wikipedia task.
  It requires source table/cell reconstruction; it is not an equivalent
  health-science gold standard.

## Implemented, verified, and withheld

The current technical audit is:
`scripts/evaluation/pin_dual_track_candidate_sources.py`.

It checks pinned archive bytes and official MD5, the ZIP member manifest,
immutable VitaminC revision and bytes, and the total test-line count.
It emits **metadata only**, to
`reports/evaluation/dual_track_candidate_source_audit.json`.
No source text, ranks, labels, evidentiary conclusions or model weights
are included. The source files stayed outside Git.

The already merged dual-track scoring harness remains unchanged.
No test gold, model scores, experimental ranking, thresholds or
statistical winner was inspected or selected.

## Decisions still requiring explicit approval before real evaluation

1. **Retrieval comparators:** a common fixed-corpus retrieval test
   (requires corpus-native adapter), or actual live multi-provider API
   discovery with a separately curated expert-labeled gold corpus.
   These experiments answer different questions and cannot be equated.
2. **Classification scope:** public VitaminC as an exploratory
   cross-domain test, or a *new* biomedical expert-labeled holdout
   for stronger domain claims. Both can be run, separately, if approved.
3. Before inspecting gold: fix primary outcomes, baseline/revisions,
   test-matching, error/abstention policy, overlap checks,
   data budgets and statistical analysis.

No preregistered metrics were chosen here and no data were represented
as independently blinded.

## Reproducibility

```sh
python -m scripts.evaluation.pin_dual_track_candidate_sources \
  --retrieval-zip /path/to/private/nfcorpus.zip \
  --classification-jsonl /path/to/private/test.jsonl \
  --output /path/to/aggregate-only/audit.json
pytest -q tests/test_candidate_source_pins.py
```

Keep original candidate bytes in the authorized temporary environment;
never attach them to normal Git commits or public CI artifacts.
