---
name: literature-evidence-mcp
description: "Use when a task needs verifiable scientific-literature metadata, DOI/citation checks, retraction lookup, full-text quote provenance, methodology screening, or a hash-chained evidence ledger through MCP. Reports traceable evidence and uncertainty; never certifies that a claim is scientifically true and never performs peer review."
argument-hint: "<research question, citation, DOI/PMCID, quote, or claim to audit>"
metadata:
  version: "0.5.0"
---

# Literature Evidence MCP

An evidence-provenance-first MCP server for scientific literature. It retrieves
metadata, validates citations and quoted text, checks retraction metadata, anchors
human annotations to source paragraphs, and writes a hash-chained evidence ledger.
It explicitly separates bibliographic facts, text matches, method-term proxies,
and scientific validation.

## When to use this skill

- Verify a DOI, title, citation, retraction status, or quoted passage.
- Search OpenAlex, Europe PMC, and Crossref and preserve provider provenance.
- Audit a review workflow with human-supplied annotations and source hashes.
- Export append-only evidence records and verify ledger integrity.

Do not use it to claim that a paper is scientifically valid, to run a PRISMA
review, or to produce a risk-of-bias judgment. Those are not implemented.

## Install and run

Requires Python 3.11+.

```bash
pip install literature-evidence-mcp
literature-evidence-mcp          # stdio; no terminal output is expected
```

Local HTTP (never expose directly to the Internet):

```bash
MCP_TRANSPORT=streamable-http MCP_PORT=8000 literature-evidence-mcp
# endpoint: http://127.0.0.1:8000/mcp
```

MCP client configuration (stdio):

```json
{
  "mcpServers": {
    "literature-evidence": {
      "command": "literature-evidence-mcp"
    }
  }
}
```

Set `OPENALEX_API_KEY` for regular OpenAlex use; keyless access has a restrictive
daily budget. Do not commit environment values.

## Key tool groups (35 tools total as of 0.5.0)

- Search and retrieval: `search_literature`, `search_literature_extended`,
  `get_paper`, `expand_citation_chain`, `find_data_and_code`
- Verification: `verify_citation`, `check_retraction`, `verify_source_quote`,
  `verify_claim`
- Methodology and statistics: `assess_methodology`, `audit_methodology`,
  `audit_pmc_methodology`, `check_statistical_reporting`
- Comparison and synthesis: `compare_studies`, `build_evidence_graph`,
  `log_review_search`, `export_bibliography`
- Evidence ledger: `export_evidence`, `verify_evidence_ledger`

The README table is the authoritative per-tool contract; call tools for their
live schemas instead of guessing parameter names.

## Recommended workflow

1. Search broadly and keep provider errors and deduplication results.
2. Resolve the exact work with `get_paper`; verify DOI/title with `verify_citation`.
3. Run `check_retraction` as a metadata check, not as a clearance certificate.
4. For quotes, use `verify_source_quote`; for literal presence use `verify_claim`.
5. Record only what you need with `export_evidence`, then run
   `verify_evidence_ledger`.
6. State `NOT_VERIFIED` / `SCREENING_ONLY` where the tools do not establish truth.

## Integrity contract

- Zero search results never prove that a paper does not exist.
- Retraction checks are metadata checks; absence is inconclusive.
- `verify_citation` checks metadata identity, not content correctness.
- `verify_claim` checks deterministic literal text presence, not scientific truth.
- Methodology tools are transparent term/phrase screens, not validated risk-of-bias
  instruments. `audit_methodology` validates human-supplied annotations.
- Full-text access is limited to trusted origins and PMC XML; there is no arbitrary
  PDF download or access-control bypass. Respect publisher licenses.
- The hash chain detects modified rows but is not externally signed; keep an
  independent checkpoint if tamper-evidence against full replacement is required.
- Raw responses are not persisted unless you explicitly log or export them.

## References

- Repository: https://github.com/Furox-Art/literature-evidence-mcp
- PyPI: https://pypi.org/project/literature-evidence-mcp/
- MCP Python SDK v2: https://py.sdk.modelcontextprotocol.io/
