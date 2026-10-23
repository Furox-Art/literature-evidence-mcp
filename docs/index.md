# Literature Evidence MCP

Literature Evidence MCP is an open-source scientific literature and evidence
provenance server for the Model Context Protocol. It searches multiple
bibliographic providers, resolves and verifies citation metadata, reads
full text where a PMCID is supplied, anchors supplied quotes and annotations to
paragraphs with hashes, and keeps a local hash-chained evidence ledger.

It is a bibliographic, traceability, and evidence-audit toolset. It is **not**
an automated peer reviewer, meta-analysis engine, certified PRISMA system, or
scientific truth oracle. It never labels a paper scientifically proven from an
abstract or citation alone, and its methodology checks are screening aids, not
formal risk-of-bias judgments. Search results are non-exhaustive, and absence of
a retraction notice is not a clearance certificate.

The current release is v0.5.1. It requires Python 3.11 or later and is installed
from source:

```bash
python -m pip install -e '.[dev]'
literature-evidence-mcp
```

## Documentation

### Evaluation and benchmarks

- [Evidence audit and benchmark protocol](benchmark-protocol.md)
- [Independent labeled science benchmarks](external_gold_evaluation.md)
- [SciFact full-corpus retrieval](scifact_full_corpus.md)
- [Two public-dataset exploratory evaluations](two_public_dataset_exploratory.md)
- [Dual-track head-to-head benchmark](dual_track_head_to_head.md)
- [Candidate datasets for independent evaluation](dual_track_candidate_sources.md)
- [Optional BM25 candidate retrieval](bm25_evidence_ranking.md)

### Evidence assessment

- [Experimental offline NLI claim-evidence triage](nli_scientific_validation.md)
- [Exploratory NLI challenger comparison](nli_challenger_comparison.md)
- [HealthVer three-class validation](healthver_three_way_validation.md)
- [HealthFC syntax-only stress test](healthfc_syntax_only_audit.md)

### Validation protocols and scope

- [Prospective cross-disciplinary validation protocol](general_science_expert_blind_validation_protocol.md)
- [Updated general-science blind validation protocol](new_expert_blind_validation_protocol.md)
- [General-science source inventory](general_science_source_inventory_20261019.md)
- [Scientific scope and residual limitations](review-science-coverage.md)

### Comparisons and features

- [Competitor audit](competitor-audit.md)
- [Live competitor smoke test](live_doi_competitor_smoke_20261019.md)
- [Four-provider discovery and citation traversal](extended_search_citation_traversal.md)
- [Bibliographic export formats](bibliography_export.md)
- [Optional native components](native-modules.md)

## Scope note

Results in these pages are exploratory unless a page explicitly says otherwise.
Public benchmark labels were not prospectively blinded, provider metadata can be
incomplete or stale, and no independent expert-labeled superiority is claimed.
