# Evidence audit and benchmark protocol (v0.3)

## Scientific interpretation

The structured `audit_methodology` and directly sourced `audit_pmc_methodology` MCP tools check **traceability of user-provided
annotations**, not scientific truth or the Cochrane RoB 2/ROBINS-I/GRADE classifications.
Caller supplies a study design, outcome, source text and quoted annotations. The tool
records source offsets and SHA-256, flags contradictory or untraceable annotations,
and abstains when evidence is unknown. A matching quote NEVER proves the research
method worked or the annotation interpretation is correct.

The separate `check_statistical_reporting` screens user-entered p values, sample
sizes and confidence interval bounds for elementary contradictions only. It does
NOT reproduce statistical analysis or produce effect size estimates. Expert
outcome-specific signaling-question review remains mandatory.

Sources: https://methods.cochrane.org/bias/resources/rob-2-revised-cochrane-risk-bias-tool-randomized-trials
and https://www.cochrane.org/authors/handbooks-and-manuals/handbook/current/chapter-08

## External ROBoto2 benchmark: independently authored source passages

External research: Hevia et al., EMNLP 2025:
https://aclanthology.org/2025.emnlp-demos.2/

Data: https://github.com/larchlab/ROBoto2/tree/main/dataset

**Dataset licensing notice:** We could not verify an explicit license in the
repository. We do not redistribute the dataset, scientific articles or quoted
excerpts. This benchmark downloads the dataset separately and writes only
aggregate figures. Verify permission and local rights before use.

Run using installed project dependencies:

```sh
curl -fsSL https://raw.githubusercontent.com/larchlab/ROBoto2/main/dataset/roboto2_dataset.csv -o /tmp/roboto2.csv
python scripts/benchmark_roboto2.py /tmp/roboto2.csv --output /tmp/roboto2-results.json
```

**Pinned SHA-256** (2026-10-18):
`636eb757884a3fcbf5a2bfca40012b016d7800099aefe4655531ae2ed91de722`

Measurement: For manual assessments with a parsed PDF and a delimited quotation
in the expert rationale, check whether the quoted fragment is present in the
PDF-parsed article body. Only quoted fragments of >=24 characters with >=5
words count; they may contain annotator comments or PDF extraction artifacts.
Wrong-article controls compare the quote to another corpus article (rotated order).
This is a constructed negative control, not external negative-label truth.

### Result, 2026-10-18

- Source articles with candidate excerpts: **93**
- Quoted excerpts: **413**
- In-source direct textual matches: **174 / 413 (42.13%)**
- Rotated cross-article matches: **0 / 413 (0%)**

Machine-readable aggregate report: `reports/roboto2-excerpt-benchmark.json`

**Interpretation:** 42.13% is observed verbatim match rate under this restrictive
protocol, NOT RoB classification accuracy or recall of true scientific evidence.
Source quotations are sometimes partial/editorialized, and PDF text is noisy.
A zero on rotated control does not prove absence of all false attribution.

## Independent outcome-label benchmark: not yet applicable

ROBoto2 publishes manually assigned RoB2 questions/domain assessments.
Our tool currently does **not** predict any RoB2 category, so no meaningful
RoB2 precision/recall score can be reported. Independent blinded scientific
assessment, train/test separation, and comparison to expert domain judgments
remain unimplemented. Future head-to-head searches also require a shared
held-out relevance gold set; comparison of provider numbers is not accuracy.

Competitor feature evidence: `docs/competitor-audit.md`.

## Direct-source paragraph bound audit

`audit_pmc_methodology(pmcid, outcome, study_design, annotations)` retrieves Europe PMC full-text XML, records the XML SHA-256, and matches annotated quotations to individual JATS paragraphs. Match offsets are local to the paragraph; any quote spanning paragraphs or found only in a heading is unverified. Incomplete source retrieval yields `NOT_VERIFIED_SOURCE_TRUNCATED`, not a false negative. Findings still require human semantic and outcome-specific assessment.
