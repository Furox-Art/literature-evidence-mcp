"""`__version__` must track the version the distribution is published under.

The protocol test compares the server's reported version with
`literature_evidence_mcp.__version__`, which proves the constant is surfaced but
not that it matches the released distribution. Without this test `__version__`
could drift from `pyproject.toml` while every other test still passed.
"""

from __future__ import annotations

import re
from pathlib import Path

from literature_evidence_mcp import __version__

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_package_version_matches_pyproject() -> None:
    text = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'(?m)^version\s*=\s*"([^"]+)"', text)
    assert match is not None, "pyproject.toml has no project version"
    assert __version__ == match.group(1)
