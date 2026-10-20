"""Mocked, provider-contract tests: never equate metadata with research truth."""
from __future__ import annotations

import httpx
import pytest

from literature_evidence_mcp import citation_traversal as ct
from literature_evidence_mcp import extended_search as es
from literature_evidence_mcp.core import (
    SEMANTIC_SCHOLAR,
    ResearchClient,
)


def work(i, *, refs=None, doi=None):
    return {
        "id": f"https://openalex.org/W{i}", "display_name": f"Synthetic {i}",
        "doi": doi if doi is not None else (
            "https://doi.org/10.1000/seed" if i == 1 else None
        ), "referenced_works": refs or [],
        "publication_year": 2022, "cited_by_count": 7,
    }


def test_s2_mapping_rejects_structural_errors_and_does_not_resolve_doi():
    with pytest.raises(TypeError):
        es._s2_paper(None)
    with pytest.raises(TypeError):
        es._s2_paper({"externalIds": ["broken"]})
    with pytest.raises(TypeError):
        es._s2_paper({"authors": {"name": "bad"}})
    good = es._s2_paper({
        "externalIds": {"DOI": "DOI:10.1234/ABC"}, "authors": [
            {"name": "Ada"}, None, {"name": "Hana"}],
        "title": "Source claim", "venue": "Synthetic", "year": 2020,
        "paperId": "A" * 40, "citationCount": 300, "abstract": "Text", "url": "https://x",
    })
    assert good["doi"] == "10.1234/abc"
    assert good["doi_status"] == "SYNTAX_VALID_NOT_RESOLVED"
    assert good["authors"] == ["Ada", "Hana"]
    assert good["citation_count_provider_reported"] == 300
    assert es._s2_paper({"externalIds": {"DOI": "bad"}})["doi_status"] == (
        "INVALID_PROVIDER_DOI_NOT_RESOLVED"
    )
    assert es._s2_paper({})["doi_status"] == "MISSING"


@pytest.mark.asyncio
async def test_four_provider_search_doi_merge_disagreement_and_doi_less(monkeypatch):
    monkeypatch.setenv("SEMANTIC_SCHOLAR_API_KEY", "fake-protected-key")
    seen_s2 = []
    def handler(req):
        if req.url.host == "api.semanticscholar.org":
            seen_s2.append(req)
            assert req.headers["x-api-key"] == "fake-protected-key"
            assert req.url.params["query"] == "neurophysiology"
            return httpx.Response(200, json={"data": [
                {"externalIds": {"DOI": "10.1000/A"}, "title": "Conflicting title",
                 "venue": "S2 journal", "year": 2023, "paperId": "s2A"},
                {"externalIds": {}, "title": "Unmatched no doi", "paperId": "s2B"},
                {"externalIds": {"DOI": "10.1000/B"}, "title": "Another", "paperId": "s2C"},
            ]})
        if req.url.host == "api.openalex.org":
            return httpx.Response(200, json={"results": [
                work(1, doi="https://doi.org/10.1000/a") | {"display_name": "Original title"}]})
        if req.url.host == "www.ebi.ac.uk":
            return httpx.Response(200, json={"resultList": {"result": []}})
        return httpx.Response(200, json={"message": {"items": []}})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        monkeypatch.setattr(es, "ResearchClient", lambda: ResearchClient(http))
        result = await es.search_four_providers("neurophysiology", 3)
    assert len(seen_s2) == 1
    assert len(result["papers"]) == 3
    merged = next(p for p in result["papers"] if p.get("doi") == "10.1000/a")
    assert merged["sources"] == ["openalex", "semantic_scholar"]
    assert any(d["field"] == "title" and d["status"] == "REVIEW_REQUIRED_NOT_RESOLVED"
               for d in merged["metadata_disagreements"])
    assert merged["journal"] == "S2 journal"
    assert merged["metadata_field_sources"]["journal"] == "semantic_scholar"
    assert result["provider_status"]["semantic_scholar"]["count"] == 3
    assert result["scientific_quality_assessed"] is False
    assert result["mode"] == "FOUR_PROVIDER_METADATA_SEARCH_NOT_VERIFIED"


@pytest.mark.asyncio
async def test_extended_source_rate_limits_fail_closed_without_erasing_other_sources(monkeypatch):
    async def no_sleep(_):
        return None
    monkeypatch.setattr("literature_evidence_mcp.core.asyncio.sleep", no_sleep)
    def handler(req):
        if req.url.host == "api.semanticscholar.org":
            return httpx.Response(429)
        if req.url.host == "api.openalex.org":
            return httpx.Response(200, json={"results": []})
        if req.url.host == "www.ebi.ac.uk":
            return httpx.Response(200, json={"resultList": {"result": []}})
        return httpx.Response(200, json={"message": {"items": []}})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        monkeypatch.setattr(es, "ResearchClient", lambda: ResearchClient(http))
        out = await es.search_four_providers("cohort")
    assert len(out["provider_status"]) == 4
    assert out["provider_status"]["semantic_scholar"]["status"] == "RATE_LIMITED"
    assert "HTTP 429" in out["provider_status"]["semantic_scholar"]["error"]
    assert out["provider_status"]["openalex"]["status"] == "OK"
    assert out["papers"] == [] and out["coverage"] == "NON_EXHAUSTIVE"


@pytest.mark.parametrize("data", [{}, {"data": None}, {"data": "not-a-list"},
                                  {"data": [None]}, {"data": [{"authors": 15}]}])
@pytest.mark.asyncio
async def test_extended_source_bad_schema_reported_not_silent(monkeypatch, data):
    def handler(req):
        if req.url.host == "api.semanticscholar.org":
            return httpx.Response(200, json=data)
        if req.url.host == "api.openalex.org":
            return httpx.Response(200, json={"results": []})
        if req.url.host == "www.ebi.ac.uk":
            return httpx.Response(200, json={"resultList": {"result": []}})
        return httpx.Response(200, json={"message": {"items": []}})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        monkeypatch.setattr(es, "ResearchClient", lambda: ResearchClient(http))
        out = await es.search_four_providers("cohort")
    assert out["provider_status"]["semantic_scholar"]["status"] == "ERROR"


@pytest.mark.asyncio
async def test_semantic_scholar_path_allowlist_and_optional_headers(monkeypatch):
    monkeypatch.delenv("SEMANTIC_SCHOLAR_API_KEY", raising=False)
    received = []
    def handler(req):
        received.append(req)
        return httpx.Response(200, json={"data": []})
    async with (httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http,
                ResearchClient(http) as client):
            with pytest.raises(ValueError):
                await client._get(SEMANTIC_SCHOLAR, "/graph/v1/paper/batch")
            with pytest.raises(ValueError):
                await client._get(SEMANTIC_SCHOLAR, "//malicious")
            assert await client._get(SEMANTIC_SCHOLAR, "/graph/v1/paper/search") == {"data": []}
    assert len(received) == 1
    assert "x-api-key" not in received[0].headers


@pytest.mark.parametrize("bad", ["fake", None, 12, "", "https://example.org/W1", "W-1"])
def test_openalex_identity_rejects_false_ids(bad):
    assert ct._work_id(bad) is None


def test_openalex_node_source_provenance():
    a = ct._node(work(1, doi="https://doi.org/10.1000/D"))
    assert a["id"] == "W1"
    assert a["doi_status"] == "SYNTAX_VALID_NOT_RESOLVED"
    assert a["scientific_content_verified"] is False
    assert ct._node(work(2))["doi_status"] == "MISSING"
    assert ct._node(work(3, doi="bad"))["doi_status"] == "INVALID_PROVIDER_DOI"
    with pytest.raises(ValueError):
        ct._node({"id": "something"})


@pytest.mark.parametrize("params", [
    {"seed_doi": "not-doi"}, {"seed_doi": "10.1000/test", "max_depth": 0},
    {"seed_doi": "10.1000/test", "max_depth": True},
    {"seed_doi": "10.1000/test", "max_depth": "2"},
    {"seed_doi": "10.1000/test", "max_per_direction": 0},
    {"seed_doi": "10.1000/test", "max_per_direction": True},
    {"seed_doi": "10.1000/test", "max_per_direction": 11},
    {"seed_doi": "10.1000/test", "directions": "inferred"},
])
@pytest.mark.asyncio
async def test_traversal_input_guards_before_any_network(params):
    with pytest.raises(ValueError):
        await ct.traverse_citations(**params)


def _good_handler(req):
    url = str(req.url)
    if "/works/https://doi.org/" in url:
        return httpx.Response(200, json=work(1, refs=[
            "https://openalex.org/W2", "https://openalex.org/W3",
            "https://openalex.org/W2", "BAD", "https://openalex.org/W9"
        ], doi="https://doi.org/10.1000/seed"))
    if req.url.params.get("filter", "").startswith("openalex:"):
        return httpx.Response(200, json={"results": [work(2), work(3)]})
    if req.url.params.get("filter") == "cites:W1":
        return httpx.Response(200, json={"results": [work(4), work(5)], "meta": {"count": 10}})
    if req.url.params.get("filter") == "cites:W2":
        return httpx.Response(200, json={"results": [work(6)], "meta": {"count": 1}})
    if req.url.params.get("filter") == "cites:W3":
        return httpx.Response(200, json={"results": []})
    if req.url.params.get("filter", "").startswith("cites:"):
        return httpx.Response(200, json={"results": []})
    return httpx.Response(200, json=work(int(url.rsplit("W", 1)[-1])))


@pytest.mark.asyncio
async def test_bidirectional_two_hops_bounded_with_provenance(monkeypatch):
    requests = []
    def handler(req):
        requests.append(str(req.url))
        return _good_handler(req)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        monkeypatch.setattr(ct, "ResearchClient", lambda: ResearchClient(http))
        out = await ct.traverse_citations("10.1000/SEED", 2, 2, "both")
    assert out["seed_work"] == "W1"
    assert out["status"] == "PARTIAL"
    assert len(out["nodes"]) >= 5 and out["nodes"][0]["id"] == "W1"
    assert ("W1", "W2") in {(edge["source"], edge["target"]) for edge in out["edges"]}
    assert ("W4", "W1") in {(edge["source"], edge["target"]) for edge in out["edges"]}
    assert out["requests_used"] <= 12
    assert out["coverage"] == "NON_EXHAUSTIVE_ONE_PAGE_PER_DIRECTION"
    assert all(edge["relation"] == "CITES_PROVIDER_ASSERTED" for edge in out["edges"])
    assert out["scientific_content_verified"] is False
    assert all(httpx.URL(uri).host == "api.openalex.org" for uri in requests)


@pytest.mark.asyncio
async def test_backward_only_missing_reference_does_not_invent_edge(monkeypatch):
    def handler(req):
        if "/works/https://doi.org/" in str(req.url):
            return httpx.Response(200, json=work(1, refs=[
                "https://openalex.org/W2", "https://openalex.org/W3"]))
        return httpx.Response(200, json={"results": [work(2)]})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        monkeypatch.setattr(ct, "ResearchClient", lambda: ResearchClient(http))
        out = await ct.traverse_citations("10.1000/seed", 1, 5, "backward")
    assert out["status"] == "PARTIAL"
    assert [e["target"] for e in out["edges"]] == ["W2"]
    assert not any(e["target"] == "W3" for e in out["edges"])


@pytest.mark.asyncio
async def test_forward_only_handles_malformed_citations_without_crash(monkeypatch):
    def handler(req):
        if "/works/https://doi.org/" in str(req.url):
            return httpx.Response(200, json=work(1))
        return httpx.Response(200, json={"results": [None, {"id": "bad"}, work(2)],
                                         "meta": {"count": 3}})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        monkeypatch.setattr(ct, "ResearchClient", lambda: ResearchClient(http))
        out = await ct.traverse_citations("10.1000/seed", directions="forward")
    assert out["status"] == "PARTIAL"
    assert len(out["edges"]) == 1 and out["edges"][0]["source"] == "W2"


@pytest.mark.asyncio
async def test_failed_root_lookup_and_wrong_root_type_are_blocked(monkeypatch):
    for response in [httpx.Response(404), httpx.Response(200, json=[]),
                     httpx.Response(200, json={"id": "evil"})]:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(lambda _req, v=response: v)
        ) as http:
            monkeypatch.setattr(ct, "ResearchClient", lambda: ResearchClient(http))
            out = await ct.traverse_citations("10.1000/seed")
            assert out["status"] == "BLOCKED_SEED_LOOKUP"
            assert out["nodes"] == [] and out["edges"] == []


@pytest.mark.asyncio
async def test_missing_references_metadata_error_preserved(monkeypatch):
    for broken in ({"referenced_works": "bad"}, {"referenced_works": ["https://openalex.org/W2"]}):
        def handler(req, broken=broken):
            if "/works/https://doi.org/" in str(req.url):
                return httpx.Response(200, json=work(1) | broken)
            return httpx.Response(200, json={"results": "not-list"})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            monkeypatch.setattr(ct, "ResearchClient", lambda: ResearchClient(http))
            out = await ct.traverse_citations("10.1000/seed", directions="backward")
        assert out["status"] == "PARTIAL"
        assert out["provider_errors"] and not out["edges"]


@pytest.mark.asyncio
async def test_bad_forward_response_preserves_unknown(monkeypatch):
    def handler(req):
        if "/works/https://doi.org/" in str(req.url):
            return httpx.Response(200, json=work(1))
        return httpx.Response(200, json={"results": "not-list"})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        monkeypatch.setattr(ct, "ResearchClient", lambda: ResearchClient(http))
        out = await ct.traverse_citations("10.1000/seed", directions="forward")
    assert out["provider_errors"][0]["relation"] == "citations"
    assert out["status"] == "PARTIAL"


@pytest.mark.asyncio
async def test_graph_no_edges_is_not_proof_of_no_citations(monkeypatch):
    def handler(req):
        if "/works/https://doi.org/" in str(req.url):
            return httpx.Response(200, json=work(1))
        return httpx.Response(200, json={"results": []})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        monkeypatch.setattr(ct, "ResearchClient", lambda: ResearchClient(http))
        out = await ct.traverse_citations("10.1000/seed")
    assert out["status"] == "PROVIDER_METADATA_RETRIEVED"
    assert out["edges"] == []
    assert out["coverage"].startswith("NON_EXHAUSTIVE")


@pytest.mark.asyncio
async def test_protocol_registers_both_tools():
    from mcp.client import Client

    import literature_evidence_mcp.server as server_module

    async with Client(server_module.mcp) as client:
        result = await client.list_tools()
        names = {item.name for item in result.tools}
        assert {"expand_citation_chain", "search_literature_extended"} <= names



@pytest.mark.asyncio
async def test_s2_same_metadata_does_not_invent_conflicts(monkeypatch):
    def handler(req):
        if req.url.host == "api.openalex.org":
            return httpx.Response(200, json={"results": [
                work(1, doi="https://doi.org/10.1000/a") | {
                    "display_name": "The Same", "publication_year": 2022,
                    "primary_location": {"source": {"display_name": "Journal"}},
                }]})
        if req.url.host == "api.semanticscholar.org":
            return httpx.Response(200, json={"data": [{
                "externalIds": {"DOI": "10.1000/a"},
                "title": "The Same", "year": 2022, "venue": "Journal",
            }]})
        if req.url.host == "www.ebi.ac.uk":
            return httpx.Response(200, json={"resultList": {"result": []}})
        return httpx.Response(200, json={"message": {"items": []}})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        monkeypatch.setattr(es, "ResearchClient", lambda: ResearchClient(http))
        out = await es.search_four_providers("synthetic")
    assert out["papers"][0]["sources"] == ["openalex", "semantic_scholar"]
    assert out["papers"][0]["metadata_disagreements"] == []


@pytest.mark.asyncio
async def test_server_wrapper_wires_four_provider_search_and_graph(monkeypatch):
    import literature_evidence_mcp.server as s

    async def search(query, size):
        return {"query": query, "size": size, "mock": True}
    async def graph(doi, depth, limit, directions):
        return {"seed_doi": doi, "depth": depth, "limit": limit,
                "directions": directions}
    monkeypatch.setattr(s, "search_four_providers", search)
    monkeypatch.setattr(s, "traverse_citations", graph)
    assert await s.search_literature_extended("topic", 4) == {
        "query": "topic", "size": 4, "mock": True
    }
    assert await s.expand_citation_chain("10.1000/a", 2, 7, "forward") == {
        "seed_doi": "10.1000/a", "depth": 2, "limit": 7,
        "directions": "forward",
    }


@pytest.mark.asyncio
async def test_existing_node_edges_are_not_lost_in_cycles(monkeypatch):
    def handler(req):
        url = str(req.url)
        if "/works/https://doi.org/" in url:
            return httpx.Response(200, json=work(1, refs=["https://openalex.org/W2"]))
        if req.url.params.get("filter", "").startswith("openalex:"):
            target = req.url.params["filter"].split(":")[1]
            if target == "W2":
                return httpx.Response(200, json={"results": [work(2, refs=[
                    "https://openalex.org/W1",
                ])]})
            return httpx.Response(200, json={"results": [work(1)]})
        if req.url.params.get("filter") == "cites:W1":
            return httpx.Response(200, json={"results": [work(2)]})
        return httpx.Response(200, json={"results": []})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        monkeypatch.setattr(ct, "ResearchClient", lambda: ResearchClient(http))
        result = await ct.traverse_citations("10.1000/seed", 2, 2, "both")
    assert {(e["source"], e["target"]) for e in result["edges"]} == {
        ("W1", "W2"), ("W2", "W1")
    }
    assert len(result["nodes"]) == 2


@pytest.mark.asyncio
async def test_frozen_node_and_request_caps_terminate_frontier(monkeypatch):
    refs = [f"https://openalex.org/W{i}" for i in range(2, 12)]
    citing = [work(i) for i in range(12, 22)]
    def handler(req):
        if "/works/https://doi.org/" in str(req.url):
            return httpx.Response(200, json=work(1, refs=refs))
        filt = req.url.params.get("filter", "")
        if filt.startswith("openalex:"):
            ids = filt.split(":", 1)[1].split("|")
            if ids[0] == "W22":
                # At this point 21 nodes are present. The 10th reference
                # must not be admitted after 30 nodes.
                return httpx.Response(200, json={"results": [
                    work(i) for i in range(22, 32)
                ]})
            return httpx.Response(200, json={"results": [
                work(int(ident[1:]), refs=[
                    f"https://openalex.org/W{i}" for i in range(22, 32)
                ]) for ident in ids
            ]})
        if filt == "cites:W1":
            return httpx.Response(200, json={"results": citing})
        return httpx.Response(200, json={"results": [work(1)]})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        monkeypatch.setattr(ct, "ResearchClient", lambda: ResearchClient(http))
        result = await ct.traverse_citations("10.1000/seed", 2, 10)
    assert result["status"] == "PARTIAL"
    assert len(result["nodes"]) == 30
    assert result["requests_used"] <= 12
    assert not any(n["id"] == "W31" for n in result["nodes"])


@pytest.mark.asyncio
async def test_request_budget_stops_backward_then_forward(monkeypatch):
    root_refs = [f"https://openalex.org/W{i}" for i in range(2, 12)]
    citing = [work(i, refs=["https://openalex.org/W1"]) for i in range(12, 22)]
    def handler(req):
        url = str(req.url)
        if "/works/https://doi.org/" in url:
            return httpx.Response(200, json=work(1, refs=root_refs))
        filt = req.url.params.get("filter", "")
        if filt.startswith("openalex:"):
            ids = filt.split(":", 1)[1].split("|")
            return httpx.Response(200, json={"results": [
                work(int(i[1:]), refs=["https://openalex.org/W1"])
                for i in ids
            ]})
        if filt == "cites:W1":
            return httpx.Response(200, json={"results": citing})
        return httpx.Response(200, json={"results": []})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        monkeypatch.setattr(ct, "ResearchClient", lambda: ResearchClient(http))
        out = await ct.traverse_citations("10.1000/seed", 2, 10)
    assert out["status"] == "PARTIAL"
    assert out["requests_used"] == 12
    assert len(out["nodes"]) == 21
    assert out["request_limit"] == 12



@pytest.mark.asyncio
async def test_forward_page_stops_exactly_at_node_cap(monkeypatch):
    root_refs = [f"https://openalex.org/W{i}" for i in range(2, 12)]
    cites_root = [work(i) for i in range(12, 22)]
    def handler(req):
        url = str(req.url)
        if "/works/https://doi.org/" in url:
            return httpx.Response(200, json=work(1, refs=root_refs))
        filt = req.url.params.get("filter", "")
        if filt.startswith("openalex:"):
            ids = filt.split(":", 1)[1].split("|")
            if ids[0] == "W22":
                return httpx.Response(200, json={"results": [work(i) for i in range(22, 30)]})
            return httpx.Response(200, json={"results": [
                work(int(i[1:]), refs=[f"https://openalex.org/W{x}" for x in range(22, 30)])
                for i in ids
            ]})
        if filt == "cites:W1":
            return httpx.Response(200, json={"results": cites_root})
        if filt == "cites:W2":
            return httpx.Response(200, json={"results": [work(30), work(31)]})
        return httpx.Response(200, json={"results": []})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        monkeypatch.setattr(ct, "ResearchClient", lambda: ResearchClient(http))
        out = await ct.traverse_citations("10.1000/seed", 2, 10)
    assert out["status"] == "PARTIAL"
    assert len(out["nodes"]) == 30
    assert not any(n["id"] == "W31" for n in out["nodes"])
    assert out["requests_used"] <= 12



@pytest.mark.parametrize("source_doi,expected_provider_doi", [
    (None, None),
    ("https://doi.org/10.1000/other", "10.1000/other"),
    ("malformed-not-a-doi", None),
])
@pytest.mark.asyncio
async def test_seed_identity_missing_mismatch_or_invalid_never_builds_graph(
    monkeypatch, source_doi, expected_provider_doi,
):
    requests = []
    def handler(req):
        requests.append(req)
        root = work(1)
        root["doi"] = source_doi
        return httpx.Response(200, json=root)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        monkeypatch.setattr(ct, "ResearchClient", lambda: ResearchClient(http))
        result = await ct.traverse_citations("10.1000/seed", 2, 3)
    assert len(requests) == 1
    assert result["status"] == "BLOCKED_SEED_IDENTITY_NOT_VERIFIED"
    assert result["nodes"] == [] and result["edges"] == []
    assert result["scientific_content_verified"] is False
    failure = result["provider_errors"][0]
    assert failure["reason"] == "SEED_DOI_MISSING_OR_MISMATCH"
    assert failure["provider_doi"] == expected_provider_doi
    assert failure["requested_doi"] == "10.1000/seed"


@pytest.mark.parametrize("status_code", [429, 500, 502, 503, 504])
@pytest.mark.asyncio
async def test_retry_exhaustion_preserves_exact_http_failure_class(
    monkeypatch, status_code,
):
    from literature_evidence_mcp.core import ProviderError
    async def no_wait(_):
        return None
    monkeypatch.setattr("literature_evidence_mcp.core.asyncio.sleep", no_wait)
    calls = []
    def handler(req):
        calls.append(req)
        return httpx.Response(status_code)
    async with (httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http,
                ResearchClient(http) as client):
        with pytest.raises(ProviderError, match=f"HTTP {status_code}"):
            await client._get(SEMANTIC_SCHOLAR, "/graph/v1/paper/search")
    assert len(calls) == 3


@pytest.mark.asyncio
async def test_retry_mixed_error_codes_keep_last_observed(monkeypatch):
    from literature_evidence_mcp.core import ProviderError
    async def no_wait(_):
        return None
    monkeypatch.setattr("literature_evidence_mcp.core.asyncio.sleep", no_wait)
    codes = iter((429, 502, 503))
    async with httpx.AsyncClient(transport=httpx.MockTransport(
        lambda _: httpx.Response(next(codes))
    )) as http, ResearchClient(http) as client:
        with pytest.raises(ProviderError, match=r"HTTP 503"):
            await client._get(SEMANTIC_SCHOLAR, "/graph/v1/paper/search")


@pytest.mark.asyncio
async def test_retry_non_429_provider_is_error_not_rate_limited(monkeypatch):
    async def no_wait(_):
        return None
    monkeypatch.setattr("literature_evidence_mcp.core.asyncio.sleep", no_wait)
    def handler(req):
        if req.url.host == "api.semanticscholar.org":
            return httpx.Response(503)
        if req.url.host == "api.openalex.org":
            return httpx.Response(200, json={"results": []})
        if req.url.host == "www.ebi.ac.uk":
            return httpx.Response(200, json={"resultList": {"result": []}})
        return httpx.Response(200, json={"message": {"items": []}})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        monkeypatch.setattr(es, "ResearchClient", lambda: ResearchClient(http))
        result = await es.search_four_providers("cohort")
    assert result["provider_status"]["semantic_scholar"]["status"] == "ERROR"
    assert "HTTP 503" in result["provider_status"]["semantic_scholar"]["error"]
    assert all(result["provider_status"][name]["status"] == "OK"
               for name in ("openalex", "europepmc", "crossref"))
