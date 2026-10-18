# HealthFC: controlled syntax-only NLI stress test

**Status:** EXPLORATORY ONLY — not prospective, blinded, clinically validated, or an expert-certified paraphrase dataset.

## Independent source and ethical use

The original [HealthFC](https://github.com/jvladika/HealthFC) dataset has 750
English/German health-claim questions, evidence sentences selected from
fact-checking articles, and expert verdicts. Cite Vladika, Schneider & Matthes
(2024), [LREC-COLING 2024](https://aclanthology.org/2024.lrec-main.709/).
Underlying materials are attributed to Medizin-transparent and University
for Continuing Education Krems. The dataset states a
**CC BY-NC-ND 4.0** license. Reuse is limited to permitted
non-commercial research; original/transformed text must not be redistributed.

- Pinned source revision: `9f31d765e5d4a99bd9fff667e82de503bc5684f5`
- Pinned source CSV SHA-256:
  `6b832bd2a73af47f7a8d9dcd3c307defa962cff3746c26b33866170a406721c8`
- Original expert label map: `0=SUPPORT`, `1=NOT ENOUGH EVIDENCE`, `2=REFUTE`.
- Original count: SUPPORT **202**, INSUFFICIENT **423**, REFUTE **125**.
- Prior **exact normalized claim** overlap check across HealthVer TRAIN/DEV/TEST:
  **0**. This does **not** rule out paraphrases or previous model pretraining.

## Frozen conversion policy and QA

The only authorized change is *question-syntax normalization*: a single
English closed question with an allowed modal/do auxiliary and an identified
predicate is converted to an affirmative hypothesis. The core NLI input still
uses the unchanged expert-selected evidence sentence(s) as premise, and the
converted claim as hypothesis. The frozen original, FEVER/ANLI and general-base
models use their pinned checkpoints and the same 0.70 confidence / 0.15 margin
rule as the previous comparison. No model is trained or deployed.

The parser is deterministic and rejects ambiguous constructions rather than
guessing. With this version's fixed syntax rule, **511/750** are converted
(SUPPORT 136, INSUFFICIENT 286, REFUTE 89); **239/750** are not evaluated.
This selected subset is **not random, not class-balanced, and not guaranteed
semantically equivalent to the original questions**. Round-trip-like syntactic
inversion tests cannot substitute for expert linguistic/medical adjudication.

Excluded categories: unsupported question forms, compound or embedded
questions, no identifiable predicate, unreliable subject boundary, and
ambiguous punctuation. Exclusions are **not errors or negative examples**.

## Execution and safeguards

The GitHub Actions workflow runs on its relevant pull request changes and can also be manually dispatched after reaching the default branch. The workflow is
`.github/workflows/healthfc-controlled-gold-audit.yml`.
It fetches the exact source and all three pinned models into an ephemeral
runner, checks source/model SHA-256, evaluates only retained records using
`scripts/evaluation/healthfc_exploratory.py`, and uploads **aggregated
metrics only**. It never uploads original HealthFC rows, transformed
claims, claim-level results, or model weights to the repository or
the result artifact. Local raw processing should likewise be ephemeral.

Any exploratory output must distinguish raw NLI predictions, abstentions,
accuracy, macro-F1, per-class recall, decision coverage, and paired
differences on the **same 511-question subset**. The previous HealthVer/SciFact
metrics **must not** be compared as if cohorts were interchangeable.

## What this cannot establish

1. Expert verdicts about *clinical evidence sufficiency* are not the
   same thing as semantic textual entailment. A gold INSUFFICIENT class
   is **not** necessarily a neutral sentence pair.
2. Some source verdicts are based on evidence available only through
   **2022**; they may no longer be clinically current.
3. The full corpus and conversion rules were inspected before comparison:
   **no confirmatory superiority or publication-grade generalization claim**.
4. All conversions still need independent **blind human semantic
   equivalence review** before confirmatory analysis; a separate new
   holdout and calibration would be necessary for production promotion.
5. Manually selected HealthFC rationale sentences bypass evidence
   retrieval and publisher authenticity checks. Negative, NULL, MIXED
   and BLOCKED results must be preserved without reinterpretation.

**Production/default NLI, registry distribution and established reports
remain unchanged.**
