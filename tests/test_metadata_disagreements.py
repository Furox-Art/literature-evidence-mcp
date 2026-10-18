"""Detect conflicting provider metadata without treating either source as ground truth."""
import httpx
import pytest

from literature_evidence_mcp.core import ResearchClient


def _crossref(*, title="Initial report", year=2022, journal="First Journal"):
    return {
        "DOI": "10.1000/abc",
        "title": [title],
        "published": {"date-parts": [[year]]},
        "container-title": [journal],
    }


def _openalex(*, title="Initial report", year=2022, journal="First Journal"):
    return {
        "doi": "https://doi.org/10.1000/abc",
        "display_name": title,
        "publication_year": year,
        "primary_location": {"source": {"display_name": journal}},
    }


def _europe(*, title="Alternative report", year="2023", journal="Other Journal"):
    return {
        "doi": "10.1000/ABC",
        "title": title,
        "pubYear": year,
        "journalTitle": journal,
        "id": "123",
    }


@pytest.mark.asyncio
async def test_conflicting_sources_are_traceable_not_auto_resolved():
    def provider(request):
        if request.url.host == "api.openalex.org":
            return httpx.Response(200, json={"results": [_openalex()]})
        if request.url.host == "www.ebi.ac.uk":
            return httpx.Response(200, json={"resultList": {"result": [_europe()]}})
        return httpx.Response(200, json={"message": {"items": [_crossref()]}})

    async with (
        httpx.AsyncClient(transport=httpx.MockTransport(provider)) as http,
        ResearchClient(http) as client,
    ):
        result = await client.search("sensible query", sources=(
            "openalex", "europepmc", "crossref",
        ))

    assert len(result["papers"]) == 1
    paper = result["papers"][0]
    assert paper["sources"] == ["openalex", "europepmc", "crossref"]
    assert paper["title"] == "Initial report"
    assert paper["year"] == 2022
    assert paper["metadata_field_sources"] == {
        "title": "openalex", "year": "openalex", "journal": "openalex",
    }
    disagreements = paper["metadata_disagreements"]
    assert {d["field"] for d in disagreements} == {"title", "year", "journal"}
    assert all(d["chosen_source"] == "openalex" for d in disagreements)
    assert all(d["other_source"] == "europepmc" for d in disagreements)
    assert all(d["status"] == "REVIEW_REQUIRED_NOT_RESOLVED" for d in disagreements)
    assert result["coverage"] == "NON_EXHAUSTIVE"


@pytest.mark.asyncio
async def test_missing_fields_fill_with_provenance_without_spurious_conflict():
    def provider(request):
        if request.url.host == "api.openalex.org":
            return httpx.Response(200, json={"results": [_openalex(
                title=None, year=None, journal="First Journal",
            )]})
        if request.url.host == "www.ebi.ac.uk":
            return httpx.Response(200, json={"resultList": {"result": [_europe(
                title="Initial report", year="2022", journal="first journal",
            )]}})
        return httpx.Response(200, json={"message": {"items": [_crossref(
            title=" INITIAL REPORT ", year=2022, journal="First Journal",
        )]}})

    async with (
        httpx.AsyncClient(transport=httpx.MockTransport(provider)) as http,
        ResearchClient(http) as client,
    ):
        result = await client.search("any paper", sources=(
            "openalex", "europepmc", "crossref",
        ))
    paper = result["papers"][0]
    assert paper["metadata_disagreements"] == []
    assert paper["title"] == "Initial report"
    assert paper["metadata_field_sources"]["title"] == "europepmc"
    assert paper["metadata_field_sources"]["year"] == "europepmc"
    assert paper["metadata_field_sources"]["journal"] == "openalex"


@pytest.mark.asyncio
async def test_single_source_and_abstract_fallback():
    def provider(request):
        if request.url.host == "api.openalex.org":
            return httpx.Response(200, json={"results": [
                {**_openalex(title=None, year=None, journal=None),
                 "abstract_inverted_index": {"method": [0], "test": [1]}}
            ]})
        return httpx.Response(200, json={"message": {"items": [
            _crossref(title="Study", year=2022, journal="Journal")
        ]}})
    async with (
        httpx.AsyncClient(transport=httpx.MockTransport(provider)) as http,
        ResearchClient(http) as client,
    ):
        solo = await client.search("theory", sources=("openalex",))
        combined = await client.search("theory", sources=("crossref", "openalex"))
    assert solo["papers"][0]["metadata_disagreements"] == []
    assert solo["papers"][0]["metadata_field_sources"] == {}
    assert combined["papers"][0]["abstract"] == "method test"
    assert combined["papers"][0]["metadata_disagreements"] == []
    assert combined["papers"][0]["metadata_field_sources"]["title"] == "crossref"
