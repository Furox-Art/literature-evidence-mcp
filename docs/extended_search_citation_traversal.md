# Four-provider metadata discovery and bounded citation traversal

**Status:** opt-in technical features. **No scientific claim verification, systematic review
completeness, retrieval superiority, risk-of-bias decision or automated relevance ranking.**

## 1. Extended literature discovery

`search_literature_extended(query, limit_per_source=10)` runs **OpenAlex,
Europe PMC, Crossref, and Semantic Scholar** searches concurrently. The original
`search_literature` (three providers) remains unchanged.

Semantic Scholar's documented Graph API is queried only at its approved
`/graph/v1/paper/search` endpoint. Each provider has independent
`provider_status` and errors. Optional environment variable
`SEMANTIC_SCHOLAR_API_KEY` can authenticate that service; no embedded API keys
or credentials are stored in Git.

- Records with **syntactically valid DOI values** may be reconciled by DOI;
  missing or malformed DOI values are not grouped by titles.
- Contradictory paper titles, years and journals are flagged with field
  provenance rather than silently overwritten.
- OpenAlex, Europe PMC and Crossref use the existing bounded HTTP client,
  streaming limits, retries, approved host/path restrictions and timeout.
- Semantic Scholar 429/rate-limit, 403, 404 or schema errors return an explicit
  provider `ERROR` status, not an empty-paper claim.
- Results are **non-exhaustive**; provider ranking has not been tested against
  expert-judged retrieval relevance.

Example MCP call (non-identifying synthetic query):

```json
{"query": "synaptic plasticity meta analysis", "limit_per_source": 5}
```

## 2. Forward and backward citation chain

`expand_citation_chain(seed_doi, max_depth=1, max_per_direction=5,
directions="both")` traverses OpenAlex *provider-asserted* citation edges:

- `backward`: references *cited by* the inspected paper
  (`referenced_works`). Edge points from citing paper to cited work.
- `forward`: papers *that cite* the inspected paper
  (`filter=cites:W...`). Edge points from citing paper to cited work.
- `both`: inspect both directions; `max_depth` 1 or 2. Breadth-first
  traversal is deterministic relative to the provider's returned order.
- Hard ceilings: at most **12 OpenAlex HTTP calls**, **30 graph nodes**,
  and **10 returned entries per direction** at any frontier work.
- Nodes retain OpenAlex source identifiers, source year, DOI status and
  provider-reported citation counts. Edges retain `evidence_source`,
  `observed_at_depth` and `CITES_PROVIDER_ASSERTED` status.
- Returned graph status is `PARTIAL` when a request fails, a page/count
  suggests truncation, or a cap is reached. If the seed cannot be resolved,
  the explicit state is `BLOCKED_SEED_LOOKUP`.
- **Zero edges never imply zero real-world citations.** The API's
  bibliographic relationships are neither direct full-text citation
  context verification nor a measure of a paper's scientific validity.

Example:

```json
{
  "seed_doi": "10.1038/nature12373",
  "max_depth": 2,
  "max_per_direction": 4,
  "directions": "both"
}
```

## Evidence and reproducibility boundaries

- Existing NLI engines, scientific thresholds, HealthVer/SciFact/HealthFC
  reports, metadata defaults, review workflows, and package publication
  settings remain unchanged.
- Neither tool performs automated *multi-round ranking*, citation-based
  relevance inference, independent publication-authenticity checks,
  missing-citation assertions, or scientific evidence synthesis.
- Providers may update their bibliographic content between calls; the
  output includes `checked_at`, source IDs, partial-state warnings and
  provider error records, **not a frozen bibliographic ground truth**.
- No raw research dataset or model weights are committed.

WSL live smoke on 2026-10-19: OpenAlex successfully returned **5 nodes and
4 citation edges** for the example DOI, explicitly **PARTIAL** due to
bounded retrieval. All three original search providers returned 2 results
each for a small exploratory query; Semantic Scholar returned an explicit
rate-limit-related provider error, so its production availability was **not
verified**. This smoke is not a scored benchmark.

Reference API contracts: [OpenAlex API recipes](https://help.openalex.org/how-to/api-recipes/)
and [Semantic Scholar Graph API](https://api.semanticscholar.org/api-docs/).

## Test and QA commands

```sh
pytest -q tests/test_extended_search_citations.py tests/test_mcp_protocol.py
pytest -q --cov=literature_evidence_mcp --cov-branch --cov-fail-under=100
npm test --prefix packages/npm
```

Mock-transport regressions exercise host allowlists, injected malicious
provider data, DOI conflicts, rate limits, errors, citation directions,
cycles, traversal caps and preservation of unknown states.
