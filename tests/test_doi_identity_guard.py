"""Provider metadata cannot turn a title or malformed DOI into a work identity."""

import httpx
import pytest

from literature_evidence_mcp.core import ResearchClient


@pytest.mark.asyncio
async def test_mixed_valid_doi_spellings_merge_one_work_without_claiming_resolution():
    def provider(request):
        if request.url.host == "api.openalex.org":
            return httpx.Response(200, json={"results": [{
                "doi": "HTTPS://DOI.ORG/10.1000/ABC",
                "id": "https://openalex.org/W100", "display_name": "Study",
            }]})
        if request.url.host == "www.ebi.ac.uk":
            return httpx.Response(200, json={"resultList": {"result": [{
                "doi": "10.1000/ABC", "title": "Study", "id": "1234",
            }]}})
        return httpx.Response(200, json={"message": {"items": [{
            "DOI": "doi:10.1000/ABC", "title": ["Study"],
        }]}})

    async with (
        httpx.AsyncClient(transport=httpx.MockTransport(provider)) as http,
        ResearchClient(http) as researcher,
    ):
        result = await researcher.search("published trial", sources=(
            "openalex", "europepmc", "crossref",
        ))
    assert len(result["papers"]) == 1
    paper = result["papers"][0]
    assert paper["doi"] == "10.1000/abc"
    assert paper["doi_status"] == "SYNTAX_VALID_NOT_RESOLVED"
    assert paper["doi_provider_value"] == "HTTPS://DOI.ORG/10.1000/ABC"
    assert paper["sources"] == ["openalex", "europepmc", "crossref"]
    assert paper["metadata_disagreements"] == []


@pytest.mark.asyncio
async def test_invalid_doi_never_merges_across_providers_even_with_matching_title():
    def provider(request):
        if request.url.host == "api.openalex.org":
            return httpx.Response(200, json={"results": [{
                "doi": "https://evil.example/10.1000/abc", "display_name": "Study",
                "id": "W5",
            }]})
        if request.url.host == "www.ebi.ac.uk":
            return httpx.Response(200, json={"resultList": {"result": [{
                "doi": "10.1000/abc?tracking=true", "title": "Study", "id": "P5",
            }]}})
        return httpx.Response(200, json={"message": {"items": [{
            "DOI": "not-a-doi", "title": ["Study"],
        }]}})

    async with (
        httpx.AsyncClient(transport=httpx.MockTransport(provider)) as http,
        ResearchClient(http) as researcher,
    ):
        papers = (await researcher.search("research methods"))["papers"]
    assert len(papers) == 3
    assert {p["source"] for p in papers} == {"openalex", "europepmc", "crossref"}
    assert all(p["doi"] is None for p in papers)
    assert all(p["doi_status"] == "INVALID_PROVIDER_DOI_NOT_RESOLVED" for p in papers)
    assert {p["doi_raw"] for p in papers} == {
        "https://evil.example/10.1000/abc", "10.1000/abc?tracking=true", "not-a-doi",
    }
    assert all(len(p["sources"]) == 1 for p in papers)


@pytest.mark.asyncio
async def test_missing_doi_same_source_same_title_is_not_identity():
    def provider(request):
        return httpx.Response(200, json={"results": [{
            "doi": None, "id": "https://openalex.org/W1", "display_name": "Untitled",
        }, {
            "doi": None, "id": "https://openalex.org/W2", "display_name": "Untitled",
        }, {
            "id": "https://openalex.org/W3", "display_name": "Untitled",
        }]})

    async with (
        httpx.AsyncClient(transport=httpx.MockTransport(provider)) as http,
        ResearchClient(http) as researcher,
    ):
        papers = (await researcher.search("different works", sources=("openalex",)))["papers"]
    assert len(papers) == 3
    assert all(p["doi"] is None and p["doi_status"] == "MISSING" for p in papers)
    assert [p["source_id"] for p in papers] == [
        "https://openalex.org/W1", "https://openalex.org/W2", "https://openalex.org/W3",
    ]
    assert all(p["metadata_disagreements"] == [] for p in papers)
