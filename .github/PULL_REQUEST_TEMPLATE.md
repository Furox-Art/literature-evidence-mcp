<!--
Thanks for contributing. Read CONTRIBUTING.md first. Do not commit API keys,
credentials, confidential papers, or private paths. Changes to scientific
verdict logic need an evaluation protocol, expert review, and explicit
false-positive reporting.
-->

## What this changes

<!-- One paragraph. What is different after this merges, and for whom. -->

Closes #

## Area

- [ ] MCP tool or server behaviour (`src/literature_evidence_mcp/`)
- [ ] Tests (`tests/`)
- [ ] Evidence ledger, provenance, or export
- [ ] Provider integration or network handling
- [ ] npm / Node.js adapter (`packages/npm/`)
- [ ] Native component (`native/`)
- [ ] Scientific evaluation or benchmark protocol
- [ ] Packaging, CI, or performance
- [ ] Documentation (`README.md`, `docs/`, `CONTRIBUTING.md`)

## Scientific integrity

Tick what this change preserves. If none apply, explain why in the evidence
section.

- [ ] UNKNOWN and NOT_VERIFIED remain explicit for unsupported conclusions.
- [ ] Metadata, text matching, and keyword screening are still not presented as scientific validation.
- [ ] Provider errors, missing results, and truncation remain explicit rather than becoming silent success.
- [ ] New or changed verdict logic has an evaluation protocol and explicit false-positive reporting.
- [ ] Expert review is planned or completed for changes to scientific judgement.
- [ ] Not applicable; no behaviour or scientific claim changed.

## Evidence

This is the part that matters most. What proves the change is correct, beyond
the test suite?

<!--
Paste the command and its real output. If this is documentation-only, say which
test proves the documentation is true. For provider-dependent changes, include
the redacted request and response, and state whether the test was live or mocked.
-->

```
```

## Checks run

Paste results, including exit codes.

- [ ] `python -m pip install -e '.[dev,retrieval]'`
- [ ] `pytest -q --cov=literature_evidence_mcp --cov-branch --cov-report=term-missing --cov-fail-under=100`
- [ ] `pytest -q tests/test_mcp_protocol.py -rs`
- [ ] `python -m compileall -q src`
- [ ] `python -m build`
- [ ] `npm test --prefix packages/npm` (if `packages/npm/` changed)
- [ ] Native component tests from `.github/workflows/ci.yml` (if `native/` changed)
- [ ] Not applicable

```
```

## Review notes

<!--
Anything a reviewer should look at first, anything you deliberately left out,
and anything you are unsure about. Saying "I am not sure this is right" is more
useful here than a confident guess.
-->
