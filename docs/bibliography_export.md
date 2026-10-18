# Bibliographic interoperability: BibTeX, RIS and CSL-JSON

The opt-in `export_bibliography` MCP tool serializes up to **100 caller-supplied**
bibliographic records into three common reference-management formats:

- **BibTeX**: conventional `@article`/`@misc` entries, with TeX reserved
  characters escaped to prevent field/control-sequence injection.
- **RIS**: one `TY` / `TI` / `AU` / `JO` / `PY` / `DO` record per work.
  Newlines and control characters in untrusted fields are normalized first.
- **CSL-JSON**: JSON citation objects with `title`, `issued`,
  `container-title`, `DOI`, `author` names as literal values and unique IDs.
  This is a reference-format export, **not a Zotero synchronization connector**.

The tool accepts the standardized paper dictionaries already returned by
`search_literature` or `get_paper`, with fields `title` (required),
`authors` (list), `journal`, `year`, and `doi`. The caller may provide
`metadata_disagreements` from cross-provider search.

### MCP example

```json
{
  "papers": [{
    "title": "Synthetic example: unverified sample study",
    "authors": ["Ada Example", "Alex Test"],
    "journal": "Example Journal",
    "year": 2024,
    "doi": "10.1234/example.0001"
  }],
  "output_format": "csl-json"
}
```

Choose `bibtex` (default), `ris` or `csl-json`. The response includes
the encoded `content`, `record_count`, a `records` audit array with
per-item `doi_status`, `fields_exported`, `metadata_conflicts_present`,
and an explicit `scientific_claim_verified=false` / `doi_resolved=false`.

### Scientific and data integrity limits

- **No network access** and no fresh DOI or publisher authentication occurs.
  `SYNTAX_VALID_NOT_RESOLVED` means DOI format is valid, **not resolved**.
  Malformed DOI metadata is deliberately omitted and marked
  `INVALID_DOI_OMITTED`.
- **No inferred fields**: missing authors, journal, year or DOI are omitted.
  Independently supplied DOI-less records are **not merged by title**; keys
  are unique and stable within each call, not guaranteed globally.
- **Metadata disagreements remain visible** as an explicit audit flag.
  Conversion is not authoritative bibliographic verification.
- **No human reference manager connected**: exports are importable citation
  representations, not evidence of success importing them into any external
  product. BibTeX Unicode import compatibility depends on the client's TeX
  engine.
- **No scientific endorsement**: an accurately formatted citation cannot
  establish causal validity, risk of bias, study quality or scientific truth.
  This feature is orthogonal to HealthVer, SciFact and HealthFC metrics.

### Reproducibility

```sh
python -m pytest -q tests/test_bibliography.py tests/test_mcp_protocol.py
pytest -q --cov=literature_evidence_mcp --cov-branch --cov-fail-under=100
```

The MCP interface is also exercised through the real Python and TypeScript
client protocol tests in CI. The feature adds no third-party runtime package
and performs no npm Registry publication.
