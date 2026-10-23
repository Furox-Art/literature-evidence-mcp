"""Regression tests for directly traceable source spans and atomic evidence records."""
from __future__ import annotations

import asyncio
import hashlib

import httpx
import pytest

from literature_evidence_mcp.core import CROSSREF, EvidenceLedger, ProviderError, ResearchClient


@pytest.mark.asyncio
async def test_fulltext_stable_quote_provenance_and_nested_sections():
    raw = b'''<article><front><article-meta><title-group><article-title>Example study</article-title>
    </title-group></article-meta></front><body><sec><title>Findings</title>
    <p>The prespecified primary outcome was null.</p><sec><title>Sub-analysis</title>
    <p>Exploratory associations were reported.</p></sec></sec>
    <p>Unsectioned paragraph.</p></body></article>'''
    async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda _: httpx.Response(200, content=raw))) as http, ResearchClient(http) as client:
        record = await client.fulltext("PMC123")
        result = await client.source_quote("PMC123", "primary outcome was null")
    assert record["sha256_xml"] == hashlib.sha256(raw).hexdigest()
    assert record["paragraph_count"] == 3
    assert len(record["spans"]) == 3
    assert [x["section"] for x in record["spans"]] == [
        "Findings", "Sub-analysis", "Unsectioned body"]
    span = record["spans"][0]
    assert record["content"][span["offset_start"]:span["offset_end"]] == span["text"]
    assert result["status"] == "TEXTUAL_MATCH_ONLY"
    assert len(result["matched_spans"]) == 1
    assert result["matched_spans"][0]["span_id"] == "PMC123:p1"
    assert result["scientific_claim_verified"] is False


@pytest.mark.asyncio
async def test_fulltext_truncation_maintains_span_alignment():
    raw = (b"<article><body><sec><title>Methods</title><p>First evidence here.</p>"
           b"<p>Second evidence is later.</p></sec></body></article>")
    async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda _: httpx.Response(200, content=raw))) as http, ResearchClient(http) as client:
        result = await client.fulltext("PMC123", max_chars=32)
    assert result["truncated"] is True
    assert result["paragraph_count"] == 2
    assert result["spans"][0]["span_id"] == "PMC123:p1"
    assert len(result["spans"]) == 1


@pytest.mark.asyncio
async def test_ledger_parallel_writers_preserve_chain(tmp_path):
    path = tmp_path / "evidence.jsonl"
    writers = [EvidenceLedger(path) for _ in range(30)]
    receipts = await asyncio.gather(*(
        writers[i].append("source_quote", {"index": i}) for i in range(30)))
    assert sorted(x["entry_number"] for x in receipts) == list(range(1, 31))
    assert EvidenceLedger(path).verify()["status"] == "VALID"
    assert EvidenceLedger(path).verify()["count"] == 30


@pytest.mark.asyncio
async def test_stream_capped_before_buffering():
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _:
            httpx.Response(200, content=b"x" * 2_000_001))) as http, ResearchClient(http) as client:
        with pytest.raises(ProviderError, match="too large"):
            await client._get(CROSSREF, "/works")


@pytest.mark.asyncio
async def test_source_quote_missing_does_not_invent_scientific_verdict():
    raw = b"<article><body><sec><p>Null result.</p></sec></body></article>"
    async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda _: httpx.Response(200, content=raw))) as http, ResearchClient(http) as client:
        result = await client.source_quote("PMC2", "statistically significant")
    assert result["status"] == "NOT_VERIFIED"
    assert result["matched_spans"] == []
    assert result["scientific_claim_verified"] is False
