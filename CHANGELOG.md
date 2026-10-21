# Changelog

Release notes for literature-evidence-mcp. Versions before 0.5.1 were not
tracked in this file.

## 0.5.1 - 2026-10-21

### Release integrity

- The 0.5.0 artifacts on PyPI were uploaded on 2026-10-19T22:42Z from the
  `4d40dae` source tree, before the `v0.5.0` tag existed. The tag-based
  checkout therefore does not describe the published 0.5.0 artifacts.
- The published 0.5.0 artifacts do not contain the `citation_traversal`
  request-budget fix from `9771e3a`: `fetch()` now refuses a thirteenth
  request through a single `_RequestBudgetExhausted` path, and the
  unreachable backward-direction budget guard was removed. A tag-based
  build of 0.5.0 would contain that code, so tag and PyPI artifact were
  not equivalent.
- 0.5.1 must be built from the tagged commit, with the tag created before
  publication, so the tag and the PyPI artifacts describe the same tree. The
  published artifacts must contain the `citation_traversal` fix; do not
  rebuild 0.5.0 from the tag and treat it as the published artifact.

### Fixed

- Enforce the twelve-request citation-traversal budget in one place and
  mark traversal output incomplete when the budget is exhausted
  (`9771e3a`).
- Apply the remaining CodeQL hardening and test changes from
  `9771e3a` and `9df3d39` that landed after the 0.5.0 upload.

### Docs

- Add the `SKILL.md` agent skill manifest with version metadata 0.5.1
  (`0e60299`).
- Correct the README adapter heading to v0.5.1 and update both adapter
  tool-count references from 20 to the 35 tools registered by the server.
