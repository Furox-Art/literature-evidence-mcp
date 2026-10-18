# Literature Evidence MCP — TypeScript adapter

This is the **npm / Node.js MCP stdio adapter** for the Python scientific literature and evidence-traceability engine in [`Furox-Art/literature-evidence-mcp`](https://github.com/Furox-Art/literature-evidence-mcp).

It does **not** reimplement scientific evaluations or make correctness claims. All 17 Python tools are discovered and forwarded dynamically, retaining their JSON schemas, error states, evidence provenance, and results.

## Install and run

**Python 3.11+ and Node.js 22+ are both required.** After both packages have been published to their registries, install them:

```sh
python -m pip install literature-evidence-mcp
npm install -g @furox-scientific/literature-evidence-mcp
literature-evidence-mcp-ts
```

Until registry publishing is independently verified, install both packages from this repository checkout:

```sh
python -m pip install -e .
npm install -g ./packages/npm
```

If the Python executable is not available as `python3` (Unix) or `python` (Windows), set `LITERATURE_EVIDENCE_PYTHON` to its absolute path. Python core installation from PyPI is only usable once its release is published; until then install from the GitHub source:

```sh
python -m pip install 'git+https://github.com/Furox-Art/literature-evidence-mcp.git'
```

Example MCP host configuration:

```json
{
  "mcpServers": {
    "literature-evidence": {
      "command": "literature-evidence-mcp-ts",
      "env": {
        "LITERATURE_EVIDENCE_PYTHON": "/absolute/path/to/python"
      }
    }
  }
}
```

The TypeScript adapter always runs the Python backend over local **stdio**. It does not expose unauthenticated HTTP endpoints or download executables. An inherited `MCP_TRANSPORT` value is overridden to `stdio` for the Python child. The npm adapter is not a substitute for installing Python core dependencies.

## Development

```sh
npm ci
npm run build
npm test
```

GitHub CI runs real Node-to-Python MCP protocol tests plus 100% Python statement and branch coverage. The TypeScript adapter is separately checked for 100% V8 line, branch, and function coverage. Do not treat line coverage as proof of scientific validity or correct bibliography.

License: Apache-2.0.
