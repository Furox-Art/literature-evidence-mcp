# Literature Evidence MCP

An open-source **scientific literature and evidence provenance** MCP server.

> **Important:** v0.3 is a **bibliographic/traceability and evidence-audit MVP**, NOT an automated peer reviewer, meta-analysis engine, PRISMA-compliant review engine, validated quality score, or scientific truth oracle. It never labels a paper scientifically proven solely from an abstract or citation.

## Features implemented in v0.3

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
| `audit_methodology` | Outcome-specific source-anchored HUMAN-SUPPLIED annotation validation. Flags untraceable/contradictory evidence; never infers formal RoB2/ROBINS-I judgments. |
| `audit_pmc_methodology` | Fetches Europe PMC full-text JATS XML by PMCID and independently anchors human annotations to exact paragraphs with source SHA-256; handles truncated sources explicitly. |
| `check_statistical_reporting` | Screens user-supplied p values, sample sizes and CI range inconsistencies; does NOT recompute analyses. |
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
. .venv/bin/activate                     # Linux/macOS
# Windows PowerShell: .\.venv\Scripts\Activate.ps1
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
- Hash-chain is not independently authenticated; keep external checkpoints if you need tamper-evidence against complete log replacement. v0.3 serializes writers across processes using a local lock file; it cannot guarantee atomic behavior on all network filesystems.

## Current limitations and roadmap (NOT YET IMPLEMENTED)

1. Evaluate API coverage/precision against independently labeled benchmark queries and monitor API drift.
2. Page/figure/table provenance from licensed PDFs and JATS XML; v0.2 supports paragraph-level XML spans only.
3. Human-supervised formal RoB 2, ROBINS-I, GRADE; v0.3 adds cited annotation traceability and numerical field screens but NOT validated risk judgments or statistical reproduction.
4. Citation graph with verified edge provenance and correction/retraction propagation.
5. PRISMA 2020-compatible reviewer double-screening and export.
6. Audited quantitative extraction/meta-analysis with independent statistical tests and uncertainty.
7. API rate accounting, request queueing, persistent cache, integration/security hardening and authenticated hosting.
8. Obtain a blind expert-labeled retrieval and risk-of-bias test set; current ROBoto2 excerpt-match audit and 3-query competitor smoke cannot prove accuracy superiority.

## v0.3 evidence audit and external evaluations

- 17 MCP tools (3 new: `audit_methodology`, `audit_pmc_methodology`, `check_statistical_reporting`).
- External ROBoto2 benchmark: **174 of 413** delimited expert quote excerpts were located verbatim in PDF-parsed article text across **93 studies** (**42.13%**); 0/413 rotated control matches. This is NOT bias-judgment or scientific accuracy; quoted reviewer notes and PDF parses can differ. Dataset licensing not verified; raw dataset is not redistributed. See [benchmark protocol](docs/benchmark-protocol.md) and [aggregate report](reports/roboto2-excerpt-benchmark.json).
- Same-query, same-provider retrieval smoke tests comparing this MCP, Athenaeum, and Paper Search MCP are recorded in [competitor audit](docs/competitor-audit.md) and `reports/live-*.json`. Counts and times are not expert relevance metrics, and no performance dominance is asserted.

## Testing

Offline deterministic tests mock every external provider and check concurrent ledger writers, covering DOI validation, error handling, failure isolation, ambiguous status reporting, ledger corruption, method-screening caveats and evidence graph validation.

**Verification:** On 2026-10-18, 20 baseline v0.2 tests passed with the real MCP v2 SDK in a connected development environment, including in-process MCP tool discovery/call. The opt-in `python scripts/live_smoke.py` also passed for OpenAlex, Europe PMC and Crossref. CI does not run live provider checks. Hosted Streamable HTTP, production resilience, source accuracy, formal risk-of-bias validity, and competitive superiority have NOT been independently verified.

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
## v0.3 technical change log

- Real Europe PMC XML paragraph source-bound annotation audit, distinguishing incomplete retrieval from proven absence; never claims RoB2 assessment.
- 98 deterministic unit and protocol tests; 100% Python statement and branch coverage on local Python 3.12, including error paths. GitHub CI enforces 100% across Python 3.11, 3.12 and 3.13.

- Human-supplied outcome-specific methods evidence traceability; unknowns and contradictions explicit.
- Mechanical checks for invalid p-values, sample sizes and interval bounds; no fabricated inferential statistics.
- Pinned external ROBoto2 research benchmark with aggregate report, licensing caveat and non-comparable RoB category warning.
- Three-engine public-provider retrieval smoke and evidence-based competitor feature matrix; no claimed superiority.

## Coverage policy (strict)

The CI workflow runs the complete deterministic suite with both statement and branch coverage. The fail-under threshold is **100%** across all packaged Python code; no modules, files, functions, or error paths are excluded via coverage omit directives or pragma flags. Code changes must add executable tests covering every new line and branch before merging. Coverage is not equivalent to scientific or statistical validity.

Reproduce locally:

```sh
pytest -q --cov=literature_evidence_mcp --cov-branch --cov-report=term-missing --cov-fail-under=100
```

## v0.3.1: live full-text negotiation and guarded literal citation matching

- Fixed Europe PMC `fullTextXML` HTTP content negotiation: XML requests use `Accept: application/xml` instead of the JSON default, which previously produced `406 Not Acceptable` in live calls. Live smoke on 2026-10-18 retrieved 47 XML paragraphs from `PMC7121925` and verified a sourced paragraph quote; external API availability may change.
- Aligned quoted-text checks across `verify_claim`, `verify_source_quote` and methodology audits. Case-insensitive and whitespace-flexible comparison now requires intact Unicode word boundaries where a quoted token begins or ends with a word character. The word `significant` can no longer be verified from `insignificant`, nor `effective` from `ineffective`. Punctuation in quoted snippets remains literal.
- Both direct-text and Europe PMC JATS quote lookups return start/end character offsets (direct text or local paragraph) and source hashes; absence from truncated XML is explicitly marked `NOT_VERIFIED_SOURCE_TRUNCATED`. No claim of scientific validity or inferred method quality is introduced.
- The GitHub CI gate remains **100% statement AND branch coverage** on Python 3.11, 3.12 and 3.13; no coverage exclusions.

## v0.3.2: strict work identity guards for literature search

- Search results now normalize DOI text using the same validated canonical syntax as direct DOI lookups. DOI URL prefixes and case variants are normalized before merging provider records. `SYNTAX_VALID_NOT_RESOLVED` explicitly means the DOI *shape* passed validation, **not** that the DOI or scientific claim was independently resolved.
- Untrusted provider DOI values that fail validation are preserved as `doi_raw` with `doi_status=INVALID_PROVIDER_DOI_NOT_RESOLVED`, while the normalized `doi` value is `null`. No cross-provider aggregation is performed on invalid DOI strings.
- Work records with no DOI are kept separate, even when providers report identical titles or the same provider returns repeated titles. Their `doi_status=MISSING` denotes missing evidence of work identity, not evidence that no DOI exists.
- Provider disagreements and source provenance from v0.3.1 remain visible. No metadata consistency check or DOI format validation is a scientific truth verdict.
- **Quality gate unchanged:** 100% statement and branch coverage across Python 3.11, 3.12 and 3.13, including DOI normalization and all error paths.

## Node.js / TypeScript MCP adapter (v0.3.2)

An optional **TypeScript v2 MCP stdio front end** is available under [`packages/npm`](packages/npm). It dynamically discovers the Python server's available MCP tools (20 in v0.4), forwards their input schemas and result/error statuses unchanged, and keeps all scientific decisions in the Python core. It provides a Node/npm integration point without rewriting or duplicating the scientific methodology. **Both Python and Node.js are required; this is not a standalone TypeScript scientific engine.**

From a checked-out repository:

```sh
python -m pip install -e .
npm install --prefix packages/npm
npm run --prefix packages/npm build
LITERATURE_EVIDENCE_PYTHON=python3 node packages/npm/dist/cli.js
```

Windows users should point `LITERATURE_EVIDENCE_PYTHON` to their installed Python executable. The npm package is prepared for publication; **a successful npm registry publication is not implied** by CI success. The Python test gate remains 100% statement/branch coverage; a separate Node.js CI job checks real client-to-Python MCP protocol behavior and **100% TypeScript line/branch/function coverage**, plus package packing. The opt-in Rust text matcher was added in v0.4 (not in the original TypeScript adapter release).

## Parallel native accelerators / numerical component (v0.4)

Three independently developed components are available in native/rust_text,
native/go_sources and native/cpp_meta. Their explicit MCP endpoints are
rust_locate_quote, go_parallel_provider_status and cpp_fixed_effect_meta.
They are optional: an unavailable component returns NATIVE_NOT_INSTALLED,
and the original Python scientific pipeline remains unchanged. The TypeScript
MCP bridge dynamically discovers the now 20 Python tools. There is NO npm
registry publication in this change.

Rust matches source text, not research claims. Go probes availability of three
fixed API endpoints concurrently, not research quality. C++ computes fixed-effect
inverse-variance pooling from supplied effects and standard errors; it does not
establish study eligibility, homogeneity, bias control or causal validity.
Details: [native module instructions](docs/native-modules.md).

Quality rules: the existing Python/TypeScript CI retains 100% statement and
branch coverage. Rust enforces 100% executable-source-line coverage, Go
combines instrumented unit tests and the real CLI for 100% statements, and
C++ enforces 100% executable-source-line coverage while excluding only
noncode-only braces from GCC's mapping (explicitly reported). All native
modules have distinct integration CI jobs; no scientific superiority is claimed.


## v0.5 Review-workflow and analytical additions

29 MCP tools include new two-reviewer human RoB 2 / ROBINS-I V2 judgment
records, GRADE domain recordkeeping, two-reviewer screening, PRISMA 2020
checklist (42 reporting rows)/identification accounting, bounded supplied
PDF page text and table/image object provenance, Crossref notice propagation
without mislabeling citing papers, and C++ DerSimonian-Laird random-effects
and leave-one-out numerical calculations. Go now retrieves bounded real
metadata with a local TTL cache and five-second batch request gate.

These tools are workflow and numeric helpers: clinical methodological
accuracy, full PRISMA compliance, image/table contents and scientific truth
are NOT automatically established. See docs/review-science-coverage.md.

The CI enforces 100% Python statement/branch coverage, 100% TypeScript
line/branch/function coverage, strict Rust/Go/C++ native gates, plus
Windows and macOS native build checks. No npm registry publication.

## External independent labeled benchmark (SciFact + EvidenceBench)

**Scientific superiority was not demonstrated.** The new pinned, reproducible
[external gold evaluation](docs/external_gold_evaluation.md) runs SciFact's
labeled dev claims and EvidenceBench's 293-paper original test set, with
source SHA-256 hashes, training-only lexical threshold selection, documented
independent rank-bm25 and lexical baselines, paper/claim-cluster bootstrap
confidence intervals, and explicit absence of semantic claim predictions.
Original raw copyrighted/licensed papers and annotations are NOT stored in
the repository. CI recreates both published **aggregated** reports byte-for-byte.
No npm registry publication is performed.

## Open-corpus SciFact retrieval evaluation

A separate [full-corpus evaluation protocol](docs/scifact_full_corpus.md) measures independent BM25 and lexical retrieval across all 5,183 SciFact abstracts. The historical benchmark did **not** modify the scientific MCP; a separate opt-in local BM25 candidate ranker is now available. No unsupported science-accuracy claims are made. Aggregated results are persisted as GitHub CI artifacts and are not published to npm.

## Optional BM25 evidence candidate ranking (30th MCP tool)

`bm25_rank_evidence` uses [rank-bm25](https://pypi.org/project/rank-bm25/) to
rank **caller-supplied** paper titles and abstracts. It is not invoked by the
existing scientific methods, does not fetch publications, and cannot verify a
paper's authenticity or whether a scientific claim is supported. The
dependency is installed *only by explicit choice*:

```bash
python -m pip install -e '.[retrieval]'
```

Without that optional extra, the tool remains discoverable but returns
`OPTIONAL_BM25_NOT_INSTALLED`. No automatic installation or npm publication
takes place. See [usage, input restrictions and scientific cautions](docs/bm25_evidence_ranking.md).

## Experimental offline claim/evidence NLI (31st MCP tool)

An explicitly optional, **not clinically validated** three-way
`nli_assess_evidence` MCP tool evaluates whether a caller-supplied passage
*appears to* support, refute or provide insufficient model evidence for a
claim. The pinned, SHA-256-verified DeBERTa NLI model runs offline and never
modifies the existing source-search/quote-verification or RoB/PRISMA/GRADE
workflow. Without a configured model it abstains.

**Independent SciFact DEV audit (338 gold rationale sets):** 39.1%
non-abstaining coverage, **83.3% conditional accuracy on 132 decided
examples**, and **32.5% correct over all 338** when abstentions count as not
correct. A train-majority unconditional baseline scored **63.9%**, so no
full-coverage superiority was demonstrated. The SciFact evaluation has
**no independent insufficient-evidence class** and was given gold
source rationales; neither scientific reliability nor end-to-end
retrieval performance is established.

[Full scientific protocol, reproducibility and limitations](docs/nli_scientific_validation.md).
Optional local dependency: `pip install -e '.[nli]'`. No npm publication.


## HealthVer three-class scientific validation (external held-out labels)

The opt-in NLI tool was evaluated **without HealthVer fine-tuning or test
threshold selection** on the 1,823 human-labeled HealthVer TEST pairs:
**46.57% three-way accuracy; macro-F1 38.42%; neutral F1 58.83%**.
SUPPORT recall was only **8.20%**. On 1,694 unique claim–evidence pairs,
accuracy dropped to **43.09%**. An always-majority baseline selected using
TRAIN scored **39.88%**, so the test does **not** establish clinically
reliable fact verification or scientific superiority. Both neutral
predictions and low-confidence abstentions count as NEUTRAL for this
limited benchmarking task; they are **not proof of insufficient evidence**.

[Full HealthVer test methodology, class confusion and repeat-sensitivity
analysis](docs/healthver_three_way_validation.md). The raw HealthVer
data and large model weights are never published to the repository.
