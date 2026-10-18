# Literature Evidence MCP v0.5: scientific scope and residual limitations

This release adds auditable human-review workflows and bounded numerical or
provenance operations. It is NOT certified as a complete systematic review or
as an automated Cochrane RoB 2 / ROBINS-I V2 / GRADE rating engine.

## Risk of bias and GRADE

- record_risk_of_bias: two independent identified human reviewers, all domains,
  attributed evidence identifiers and rationale; conflicting domains require
  adjudication. No official signaling-question algorithm or independently
  calibrated assessment is implemented.
- record_grade: human-entered downgrade and upgrade domain considerations,
  an identified reviewer and rationale. No automatic final certainty category;
  threshold selection and the ROBINS-I initial-certainty conventions need experts.

References: https://www.cochrane.org/events/version-2-robins-i-tool
and https://book.gradepro.org/guideline/overview-of-the-grade-approach

## PRISMA 2020

- prisma_dual_screen: two reviewer decisions and explicit exclusion reasons,
  never force reconciliation of disagreements.
- prisma_review_flow: verifies record counts after identification/duplicate
  removal and tracks the actual **42 reporting rows / 27 main items** of
  PRISMA 2020, including 10a-b, 13a-f, 16a-b, 20a-d, 23a-d and 24a-c.
  Full-text eligibility, registration/protocol, study-level inclusion and
  adjudication remain explicitly unknown until documented by reviewers.

Reference: https://www.prisma-statement.org/prisma-2020-checklist

## Full-text PDF structural provenance

pdf_page_provenance takes only bounded base64 PDF bytes, never untrusted URLs
or filesystem paths. Returns PDF and page-text SHA-256 fingerprints, exact
page number, textual quote offsets, text bounding boxes, table rectangles
and image object bounds. It DOES NOT validate figure semantics, transcribe
images, certify table contents, authenticate publishers or bypass copyright.
Hostile documents should be parsed in sandboxed workers in production.

## Publication update alert graph

- propagation_alerts traverses user-supplied source-attributed citation edges.
- crossref_update_alerts queries Crossref update metadata, reporting
  indeterminate status when unavailable. Both generate alert chains for
  correction, retraction and expression-of-concern categories without
  relabeling downstream citing papers as retracted. Graph edges and notices
  still need independent verification.

## Quantitative analysis

cpp_random_effects implements DerSimonian-Laird inverse-variance random-effects
pooling, Q, I-squared, tau-squared, approximate normal CI, approximate
prediction interval, and optional leave-one-out refits. Known-value independent
Python comparisons and invalid numeric inputs are tested. It does not cover
REML, Hartung-Knapp, correlated estimates, meta-regression, risk of bias,
effect extraction or determination of study eligibility.

## Go retrieval and operations

go_literature_records fetches bounded real provider metadata (not just HTTP
status) concurrently for Crossref, OpenAlex and Europe PMC, using a compiled
allowlist, no redirects, fixed timeouts, result/body limits and JSON parsing.
Python adds a local SHA-keyed persistent cache with a configurable TTL, plus
cross-process one-batch-per-five-second request gating. Cache contents are
UNVERIFIED local data, not evidence, and authenticated multi-user hosting
and distributed quotas are not implemented.

## Cross-platform and performance

Rust, Go and C++ run Linux CI with independent native code tests.
GitHub also compiles native projects on Windows and macOS for portability.
The benchmark script scripts/benchmark_native.py measures only warmed
machine-specific Python/Rust literal search times and C++ DL operation times,
not identical-language speed comparisons for all features or scientific
retrieval accuracy. No claim of native acceleration superiority is made.

## What remains scientifically open

Independent expert-labeled RoB/ROBINS-I/GRADE accuracy validation; full
two-stage PRISMA retrieval, study-level inclusion/adjudication and reports;
verifiable figure/table contents; independently verified citation edges;
Hartung-Knapp/REML and publication-bias sensitivity; and tested production
authentication, multi-host resource controls and licensed PDF redistribution.
The project must not claim those are complete.

No npm Registry publication was requested or executed in v0.5.
