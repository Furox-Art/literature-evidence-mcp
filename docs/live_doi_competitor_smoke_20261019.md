# Live academic-search competitor smoke — 19 October 2026

**Three systems were actually executed**, not inferred from README feature
lists. This run measures matched live search response observations **only**.
It is **not a blinded gold-relevance evaluation**, and does not establish
scientific superiority.

## Frozen implementations and inputs

| Implementation | Git commit |
|---|---|
| Literature Evidence MCP | `3dd8735f262a73678be6e477c098cf7cb569b3bc` |
| [Athenaeum MCP](https://github.com/huuunleashed/athenaeum-mcp) | `7977804753b2854b5144ec4865fd7b6f76d23d2a` |
| [Paper Search MCP](https://github.com/openags/paper-search-mcp) | `cab1b5cc276a0cd004a0044003926a6440088049` |

Each opponent was installed in its **own Python virtual environment** under
`/tmp/literature-competitor-live-20261019`, separate from the project's
existing Python environment. The project reused its existing
`scripts/compare_search_engines.py` integration API adapters.

The exactly shared **historical** query list (not selected for favorable
results) was:

1. `cortical predictive processing`
2. `randomized controlled trial childhood anxiety`
3. `quantum entanglement bell inequalities`

Three common providers were requested from every engine: **OpenAlex,
Crossref and Europe PMC**, with five results per provider for each query,
up to 15 records per query. Engines ran during the same local session on
2026-10-19, but individual upstream API requests and cached responses were
not synchronized. No trained rankings, model thresholds, or search query
texts were changed.

## Measured observations

| Live execution | Returned records across 3 queries | DOI-bearing entries | Top-level query errors |
|---|---:|---:|---:|
| Literature Evidence MCP | 43 | 38 | 0 reported |
| Athenaeum MCP | 45 | 41 | 0 reported |
| Paper Search MCP | 44 | 39 | 0 reported |

Per-query DOI counts:

| Query | Own | Athenaeum | Paper Search |
|---|---:|---:|---:|
| Cortical predictive processing | 11 | 13 | 12 |
| Childhood anxiety RCT | 13 | 13 | 13 |
| Bell inequalities | 14 | 15 | 14 |

These numbers are **record volume, not evidence quality or recall**.
DOI agreement is also **not relevance**: observed overlaps for Own versus
Athenaeum were 11, 13 and 12 DOIs, and for Own versus Paper Search 11, 14
and 8 DOIs in query order. The report stores per-query overlap/Jaccard
without pretending that agreement identifies the correct relevant articles.

**Important limitations preserved rather than repaired silently:**

- **Athenaeum's `meta_search` can suppress per-provider exceptions** even
  when it returns top-level `OK`. Its lack of reported errors therefore
  cannot be directly compared with engines that expose provider errors.
- The research-service cache, live API updates and public quotas may affect
  response sets and wall-time. These single-pass times are recorded, but
  **not** interpreted as a reliable latency ranking.
- Existing shared-query searches are free-text requests, not direct DOI
  resolution and not the previous **fixed-corpus NFCorpus** task.
- Returned records have **no independent expert relevance labels**.
  Hence precision, completeness, health/evidence reliability and winner
  identification are **NOT EVALUATED**.
- Public query reuse, potential model/data exposure, incomplete citation
  coverage and unverified provider failure observability preclude any
  scientific superiority claim.

## Machine-readable aggregate

`reports/evaluation/live_competitor_same_query_20261019.json`

The aggregate contains engine Git SHAs, source-result file SHA-256 hashes,
shared queries, provider limits, counts, status counts, DOI overlap and
explicit negative interpretive conclusions. Full source returns and
third-party cloned repositories stay outside Git.

Reproduction (execute only on an authorized machine with network access):

```sh
python scripts/compare_search_engines.py own > /tmp/live-own.json
# In isolated pinned opponent environments:
python scripts/compare_search_engines.py athenaeum > /tmp/live-athenaeum.json
python scripts/compare_search_engines.py paper_search > /tmp/live-paper.json
# Then use scripts/evaluation/aggregate_live_doi_smoke.py
# with all three files and a frozen SHAs JSON manifest.
```

Only the actual executed three-source comparison is reported; no result was
fabricated for unexecuted Clojure or commercial research platforms.

## Next scientific gate

A **new independently collected and expert-labeled biomedical test** is
required to compare retrieved article relevance and scientific claim
classification on prospective cases. See
[expert-review intake protocol](general_science_expert_blind_validation_protocol.md).
No actual expert gold annotations exist from this work.
