# Literature Evidence MCP

An open-source **scientific literature and evidence provenance** MCP server.

> **Important:** v0.2 is a **bibliographic/traceability MVP**, NOT an automated peer reviewer, meta-analysis engine, PRISMA-compliant review engine, validated quality score, or scientific truth oracle. It never labels a paper scientifically proven solely from an abstract or citation.

## Features implemented in v0.2

| MCP tool | Status / guarantee |
| --- | --- |
| `search_literature` | OpenAlex, Europe PMC, Crossref concurrent metadata search, DOI deduplication, provider error reporting. Search is non-exhaustive. |
| `get_paper` | Crossref metadata, relations, publisher links. |
| `verify_citation` | Exact normalized DOI/title metadata match, NOT content verification. |
| `check_retraction` | Crossref `update-to` checks, including Retraction Watch updates where available. Absence is inconclusive. |
| `read_fulltext` | Europe PMC/PMC XML for supplied PMCID; records section/paragraph-span IDs, offsets, XML and paragraph SHA-256, and truncation. No PDF page claims. |
| `verify_source_quote` | Fetches Europe PMC JATS XML and returns direct matching paragraph IDs, section, and hashes; no scientific validity verdict. |
| `verify_claim` | Deterministic literal text presence only. Does not prove scientific claim. |
| `assess_methodology` | Transparent keyword/phrase screening; NOT risk-of-bias evaluation. |
| `compare_studies` | Metadata comparison, NOT conflicting results inference. |
| `find_data_and_code` | Publisher-registered Crossref links; cannot guarantee raw data/code. |
| `build_evidence_graph` | Validates explicit user-supplied nodes and evidence-referenced edges. No inferred evidence. |
| `log_review_search` | Timestamped multi-provider search log; NOT PRISMA screening. |
| `export_evidence` | Append local hash-chained JSONL evidence record with cross-process file locking. |
| `verify_evidence_ledger` | Integrity check detects modified rows; cannot detect wholesale replacement/truncation without an external signed anchor. |

## Install and run

Requires Python 3.11 or later.

```sh
python -m venv .venv
. .venv/bin/activate                # Windows: .venv\\Scripts\\activate
python -m pip install -e '.[dev]'
pytest -q
literature-evidence-mcp           # stdio; no terminal output is expected
```

Local HTTP (do not expose to the Internet without an authenticated proxy):

```sh
MCP_TRANSPORT=streamable-http MCP_PORT=8000 literature-evidence-mcp
# MCP endpoint: http://127.0.0.1:8000/mcp
```

Configure your MCP client to execute `literature-evidence-mcp` as a local subprocess. SDK: [MCP Python v2](https://py.sdk.modelcontextprotocol.io/).

OpenAlex basic queries can be keyless but have a restrictive daily budget. Obtain a key from OpenAlex and set `OPENALEX_API_KEY` for regular use. Environment variables are not committed.

## Scientific integrity and constraints

- **Exact / proxy / unknown:** tools distinguish bibliographic facts, text matches, and method-term proxies from scientific validation. All uncertain scientific conclusions remain `NOT_VERIFIED` / `SCREENING_ONLY`.
- Never interpret zero search results as evidence a paper does not exist. Providers may be unavailable, rate-limited, incomplete or stale.
- Crossref retraction check is a **metadata check**, not a global clearance certificate.
- No unrestricted URL retrieval: fixed trusted origins and API paths, DOI and PMCID validation, request timeouts, streaming response-size limits, bounded retries.
- Raw bibliographic responses are not persisted unless explicitly passed into `export_evidence` or through `log_review_search`.
- Full-text reuse and redistribution are controlled by source/publisher licenses; this server does not download arbitrary PDFs or bypass access controls.
- Hash-chain is not independently authenticated; keep external checkpoints if you need tamper-evidence against complete log replacement. v0.2 serializes writers across processes using a local lock file; it cannot guarantee atomic behavior on all network filesystems.

## Current limitations and roadmap (NOT YET IMPLEMENTED)

1. Evaluate API coverage/precision against independently labeled benchmark queries and monitor API drift.
2. Page/figure/table provenance from licensed PDFs and JATS XML; v0.2 supports paragraph-level XML spans only.
3. Human-supervised formal RoB 2, ROBINS-I, GRADE and statistical assessment; unknown values preserved.
4. Citation graph with verified edge provenance and correction/retraction propagation.
5. PRISMA 2020-compatible reviewer double-screening and export.
6. Audited quantitative extraction/meta-analysis with independent statistical tests and uncertainty.
7. API rate accounting, request queueing, persistent cache, integration/security hardening and authenticated hosting.
8. Independently benchmark against other literature MCP servers on search quality, false attribution rate and reproducibility before claiming superiority.

## Testing

Offline deterministic tests mock every external provider and check concurrent ledger writers, covering DOI validation, error handling, failure isolation, ambiguous status reporting, ledger corruption, method-screening caveats and evidence graph validation.

**Note:** These are unit tests, not successful live integrations. Real API and MCP transport tests must pass in an online CI environment before a release is claimed operational end-to-end. Optional `python scripts/live_smoke.py` exercises real providers and does not run in CI by default.

## License and contributions

Apache-2.0. See [LICENSE](LICENSE), [CONTRIBUTING.md](CONTRIBUTING.md), [SECURITY.md](SECURITY.md). Neither the license nor this repository grants rights to republish third-party scientific articles.

## Documentation references

- [MCP Python SDK v2](https://py.sdk.modelcontextprotocol.io/)
- [OpenAlex API](https://help.openalex.org/api/)
- [Crossref REST](https://api.crossref.org/swagger-ui/index.html)
- [Crossref + Retraction Watch](https://www.crossref.org/documentation/retrieve-metadata/retraction-watch/)
- [Europe PMC REST](https://europepmc.org/RestfulWebService)

## v0.2 technical change log

- Added direct full-text quote provenance (`verify_source_quote`), explicit section and paragraph IDs, UTF-8 text hashes and truncation indicators.
- Replaced unbounded HTTPX body buffering with a streamed 2 MB JSON / 4 MB XML response cap.
- Serialized evidence writes across independent callers/processes using `filelock` and `asyncio.to_thread`; the ledger still requires independently stored checkpoints for stronger guarantees.
- Added regression tests for nested sections, source offsets, missing quotations, oversized responses and concurrent writers.

**Scientific limits remain:** matching text is not proof, keyword methodology screening is not a formal bias assessment, and no independent competitor benchmark has been performed.
