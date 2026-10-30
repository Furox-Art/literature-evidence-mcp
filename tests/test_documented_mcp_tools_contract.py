"""The README's tool inventory must match the tools the server registers.

Tool counts and the numbered "MCP tool N of 35" headings drift silently when
the server grows. Both sides are parsed here rather than restated, so the test
cannot agree with a stale prose copy.
"""
from __future__ import annotations

import asyncio
import re
from functools import lru_cache
from pathlib import Path

import pytest

pytest.importorskip("mcp")

from literature_evidence_mcp.server import mcp

ROOT = Path(__file__).resolve().parents[1]
README = (ROOT / "README.md").read_text(encoding="utf-8")

NUMBERED_HEADING = re.compile(r"^## .+ \(MCP tool (\d+) of (\d+)\)$", re.MULTILINE)
COUNT_CLAIM = re.compile(r"(\d+)\s+(?:MCP|Python)\s+tools")
VERSION_PIN = re.compile(r"\((\d+)\s+in\s+v\d+\.\d+\.\d+\)")
BASELINE_ROW = re.compile(r"^\| `([a-z][a-z0-9_]*)` \|")


@lru_cache(maxsize=1)
def _registered() -> tuple[str, ...]:
    return tuple(tool.name for tool in asyncio.run(mcp.list_tools()))


def _current_sections() -> str:
    """README without the historical v0.2/v0.3 change-log sections."""
    sections = re.split(r"(?m)^(?=## )", README)
    return "\n".join(s for s in sections if not re.match(r"## v0\.(?:2|3)", s))


def _baseline_table() -> list[str]:
    section = re.search(r"(?ms)^## Core features.*?(?=^## )", README)
    assert section is not None, "README has no Core features section"
    rows = (BASELINE_ROW.match(line) for line in section.group(0).splitlines())
    return [match.group(1) for match in rows if match]


def test_every_current_tool_count_claim_matches_the_registry() -> None:
    registered = _registered()
    body = _current_sections()
    claims = [int(n) for n in COUNT_CLAIM.findall(body)]
    claims += [int(n) for n in VERSION_PIN.findall(body)]
    assert claims, "README no longer states a tool count"
    assert set(claims) == {len(registered)}, (claims, len(registered))


def test_numbered_tool_headings_name_the_tool_at_that_position() -> None:
    registered = _registered()
    headings = list(NUMBERED_HEADING.finditer(README))
    assert len(headings) >= 4
    for index, heading in enumerate(headings):
        position, total = int(heading.group(1)), int(heading.group(2))
        assert total == len(registered)
        end = headings[index + 1].start() if index + 1 < len(headings) else len(README)
        body = README[heading.end():end]
        named = next(
            (token for token in re.findall(r"`([a-z][a-z0-9_]*)`", body)
             if token in registered),
            None,
        )
        assert named is not None, f"no registered tool named under {heading.group(0)!r}"
        assert registered[position - 1] == named, (position, named, registered[position - 1])


def test_baseline_feature_table_lists_only_registered_tools() -> None:
    registered = set(_registered())
    documented = _baseline_table()
    assert len(documented) == 17
    assert set(documented) <= registered
