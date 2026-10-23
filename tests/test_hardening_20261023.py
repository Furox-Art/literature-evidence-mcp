"""Regression proofs for retraction direction, ledger locking and parallel lookups."""

from __future__ import annotations

import asyncio

import pytest

from literature_evidence_mcp import core, graph_audit
from literature_evidence_mcp.core import ResearchClient


@pytest.mark.asyncio
async def test_source_quote_rejects_a_two_character_quote() -> None:
    async with ResearchClient() as client:
        with pytest.raises(ValueError, match="3.1000"):
            await client.source_quote("PMC9", "ab")


@pytest.mark.asyncio
async def test_verify_takes_the_append_lock_and_append_locks_exactly_once(
    tmp_path, monkeypatch,
) -> None:
    acquisitions: list[str] = []
    real_lock = core.FileLock

    class TrackingLock(real_lock):  # type: ignore[misc, valid-type]
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            acquisitions.append(str(args[0]))

    monkeypatch.setattr(core, "FileLock", TrackingLock)
    ledger = core.EvidenceLedger(tmp_path / "ledger.jsonl")
    assert ledger.verify()["status"] == "VALID_EMPTY"
    assert acquisitions == []

    await ledger.append("record", {"value": 1})
    assert len(acquisitions) == 1
    assert ledger.verify()["count"] == 1
    assert len(acquisitions) == 2


class _TrackingResearch:
    active = 0
    peak = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def retraction(self, doi):
        type(self).active += 1
        type(self).peak = max(type(self).peak, type(self).active)
        await asyncio.sleep(0)
        type(self).active -= 1
        return {"status": "NO_UPDATE_IN_CHECKED_METADATA", "updated_by": []}


@pytest.mark.asyncio
async def test_notice_chain_queries_all_dois_concurrently(monkeypatch) -> None:
    _TrackingResearch.active = _TrackingResearch.peak = 0
    monkeypatch.setattr(core, "ResearchClient", _TrackingResearch)
    out = await graph_audit.crossref_notice_chain(
        ["10.1000/a", "10.1000/b", "10.1000/c"], [])
    assert _TrackingResearch.peak == 3
    assert out["alerts"] == []


class _NoticeSideOnly:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def retraction(self, doi):
        # update-to belongs to the notice itself, not to the queried article.
        return {"status": "RETRACTION_NOTICE_REPORTED", "updated_by": [],
                "updates": [{"type": "retraction"}]}


@pytest.mark.asyncio
async def test_notice_chain_does_not_mark_a_retraction_notice_as_retracted(monkeypatch) -> None:
    monkeypatch.setattr(core, "ResearchClient", _NoticeSideOnly)
    out = await graph_audit.crossref_notice_chain(
        ["10.1000/notice", "10.1000/citing"],
        [{"cited_id": "10.1000/notice", "citing_id": "10.1000/citing",
          "source_id": "crossref:cited_by"}])
    assert out["alerts"] == []
    assert out["unverified_dois"] == []
