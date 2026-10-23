# ruff: noqa: SIM117
"""Exercise failure modes and provider mapping with deterministic external transport.

No public network, no artificial coverage exclusions; error paths are real code paths.
"""
from __future__ import annotations

import httpx
import pytest

from literature_evidence_mcp.core import (
    CROSSREF,
    EUROPE_PMC,
    EvidenceLedger,
    ProviderError,
    ResearchClient,
    _as_paper,
    _limit,
    _query,
    compare_metadata,
    evidence_graph,
    screen_methodology,
    verify_quote,
)


@pytest.mark.parametrize("bad", [" ", "x", "q" * 601])
def test_search_query_guards(bad):
    with pytest.raises(ValueError):
        _query(bad)


@pytest.mark.parametrize("bad", [0, -3, 21, True, "2", 2.5])
def test_page_size_guards(bad):
    with pytest.raises(ValueError):
        _limit(bad)


def test_provider_parsing_and_raw_edge_cases():
    assert _as_paper({"title": ["A"], "published": {"date-parts": [[2022]]},
                      "author": [{"given": "A", "family": "B"}, "broken"]},
                     "crossref")["authors"] == ["A B"]
    assert _as_paper({"title": ["A"], "published": {"date-parts": []}},
                     "crossref")["year"] is None
    assert _as_paper({"display_name": "A", "abstract_inverted_index": {
        "valid": [1], "bad": [None, -1, 50000]}, "authorships": [],
        "primary_location": {"source": {"display_name": "J"}}},
        "openalex")["journal"] == "J"
    europe = _as_paper({"doi": "10.1234/X", "title": "Paper",
                        "authorString": "A, B", "id": "123",
                        "source": "PMC"}, "europepmc")
    assert europe["doi"] == "10.1234/x"
    assert europe["url"].endswith("PMC/123")
    assert _as_paper({"title": "Paper"}, "europepmc")["url"] is None
    with pytest.raises(ValueError):
        _as_paper({}, "unknown")


@pytest.mark.asyncio
async def test_owned_client_lifecycle_and_unapproved_routes():
    async with ResearchClient() as client:
        assert client._client is not None
        with pytest.raises(ValueError, match="route"):
            await client._get(EUROPE_PMC, "/invalid")
        with pytest.raises(RuntimeError, match="async with"):
            await ResearchClient()._get(CROSSREF, "/works")
    assert client._client is None


@pytest.mark.asyncio
async def test_transient_response_retries_then_succeeds(monkeypatch):
    codes = iter([503, 502, 200])
    async def no_sleep(_):
        pass
    monkeypatch.setattr("literature_evidence_mcp.core.asyncio.sleep", no_sleep)
    async with httpx.AsyncClient(transport=httpx.MockTransport(
        lambda _: httpx.Response(next(codes), json={"message": {"items": []}}))) as http:
        async with ResearchClient(http) as client:
            assert (await client._get(CROSSREF, "/works"))["message"]["items"] == []


@pytest.mark.asyncio
async def test_provider_http_status_and_network_failures(monkeypatch):
    async def no_sleep(_):
        pass
    monkeypatch.setattr("literature_evidence_mcp.core.asyncio.sleep", no_sleep)
    async with httpx.AsyncClient(transport=httpx.MockTransport(
        lambda _: httpx.Response(403))) as http, ResearchClient(http) as client:
        with pytest.raises(ProviderError, match="HTTPStatusError"):
            await client._get(CROSSREF, "/works")
    def broken(request):
        raise httpx.ConnectError("offline", request=request)
    async with httpx.AsyncClient(transport=httpx.MockTransport(broken)) as http:
        async with ResearchClient(http) as client:
            with pytest.raises(ProviderError, match="ConnectError"):
                await client._get(CROSSREF, "/works")


@pytest.mark.asyncio
async def test_source_selection_and_missing_records(monkeypatch):
    monkeypatch.setenv("OPENALEX_API_KEY", "test-key-unusable-offline")
    def handler(request):
        if request.url.host == "api.openalex.org":
            assert request.url.params["api_key"] == "test-key-unusable-offline"
            return httpx.Response(200, json={"results": [
                {"id": "id1", "display_name": "A", "doi": None,
                 "abstract_inverted_index": {"hello": [0]}}]})
        if request.url.host == "www.ebi.ac.uk":
            return httpx.Response(200, json={"resultList": {"result": [
                {"id": "id1", "title": "B"}]}})
        return httpx.Response(200, json={"message": {"items": [
            {"DOI": "10.1000/d", "title": ["D"]}]}})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        async with ResearchClient(http) as client:
            with pytest.raises(ValueError):
                await client.search("sample", sources=())
            with pytest.raises(ValueError):
                await client.search("sample", sources=("fake",))
            result = await client.search("sample", 2, sources=(
                "openalex", "europepmc", "crossref", "openalex"))
            assert all(v["status"] == "OK" for v in result["provider_status"].values())
            assert len(result["papers"]) == 3


@pytest.mark.asyncio
async def test_search_merges_missing_fields_and_provider_schema_errors():
    def handler(request):
        if request.url.host == "api.openalex.org":
            return httpx.Response(200, json={"results": [
                {"id": "W0", "doi": "https://doi.org/10.1000/p", "display_name": None}]})
        if request.url.host == "www.ebi.ac.uk":
            return httpx.Response(200, json={"resultList": {"result": [
                {"id": "P1", "doi": "10.1000/p", "title": "Biomed Title",
                 "journalTitle": "Journal", "pubYear": "2021"}]}})
        return httpx.Response(200, json={"message": {"items": [None]}})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        async with ResearchClient(http) as client:
            result = await client.search("sample", 2)
    paper = next(p for p in result["papers"] if p["doi"] == "10.1000/p")
    assert paper["title"] == "Biomed Title"
    assert paper["journal"] == "Journal"
    assert len(paper["sources"]) == 2
    assert result["provider_status"]["crossref"]["status"] == "ERROR"


@pytest.mark.asyncio
async def test_meta_and_assets_variants():
    record = {"DOI": "10.1000/data", "title": ["Study"],
              "link": [{"URL": "https://publisher.example/dataset", "content-type": "text/csv"},
                       {"content-type": "text/plain"}, "broken"],
              "relation": {"isSupplementedBy": ["x"], "unrelated": ["y"]},
              "update-to": [{"type": "correction", "DOI": "10.1000/c"}]}
    async with httpx.AsyncClient(transport=httpx.MockTransport(
        lambda _: httpx.Response(200, json={"message": record}))) as http:
        async with ResearchClient(http) as client:
            paper = await client.paper("10.1000/data")
            assert paper["paper"]["doi"] == "10.1000/data"
            assert paper["raw_fields"]["link"][0]["URL"].endswith("dataset")
            assets = await client.find_assets("10.1000/data")
            assert len(assets["links"]) == 1
            assert "isSupplementedBy" in assets["relations"]
            assert "unrelated" not in assets["relations"]
            ret = await client.retraction("10.1000/data")
            assert ret["status"] == "UPDATE_REPORTED"
            assert ret["updates"][0]["type"] == "correction"


@pytest.mark.asyncio
async def test_fulltext_invalid_empty_body_and_blank_paragraphs():
    with pytest.raises(ValueError):
        async with ResearchClient() as c:
            await c.fulltext("fake")
    for xml in [b"<article></article>", b"<article><body><p>  </p></body></article>"]:
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda _, data=xml: httpx.Response(200, content=data))) as http:
            async with ResearchClient(http) as client:
                full = await client.fulltext("PMC9")
                assert full["content"] == ""
                assert full["paragraph_count"] == 0


@pytest.mark.asyncio
async def test_quote_invalid_and_bounded_lookup():
    async with ResearchClient() as client:
        with pytest.raises(ValueError):
            await client.source_quote("PMC999", "")
    assert verify_quote("found", "found", "ref")["text_match"]
    for quote, text, ref in [("ab", "body", "ref"), ("a" * 1001, "body", "ref"),
                             ("body", "", "ref"), ("body", "body", "")]:
        with pytest.raises(ValueError):
            verify_quote(quote, text, ref)


def test_methods_graph_validation_guards():
    with pytest.raises(ValueError):
        screen_methodology("", "paper")
    with pytest.raises(ValueError):
        compare_metadata([{}] * 21)
    with pytest.raises(ValueError):
        evidence_graph([{"id": "a"}] * 251, [])
    with pytest.raises(ValueError):
        evidence_graph([{"id": ""}], [])


def test_ledger_exception_branches(tmp_path, monkeypatch):
    ledger = EvidenceLedger(tmp_path / "record.jsonl")
    ledger.file.write_text("bad json\n")
    assert ledger.verify()["status"] == "TAMPER_OR_CORRUPTION_DETECTED"
    ledger.file.write_text('{"entry_hash": "abc"}\n')
    assert ledger.verify()["status"] == "TAMPER_DETECTED"
    ledger.file.write_text('{"kind": "missing_entry_hash"}\n')
    assert ledger.verify()["status"] == "TAMPER_OR_CORRUPTION_DETECTED"
