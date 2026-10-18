"""Offline deterministic MCP integration tests with isolated mocked provider."""
from __future__ import annotations

import hashlib

import pytest

from literature_evidence_mcp import server


def _fulltext():
    text = "The assignment was randomized using a published sequence."
    return {
        "pmcid": "PMC1234",
        "title": "Randomization methods",
        "sha256_xml": "a" * 64,
        "spans": [{"span_id": "PMC1234:p1", "section": "Methods", "paragraph_index": 1,
                   "text": text,
                   "sha256_text": hashlib.sha256(text.encode()).hexdigest()}],
        "truncated": False,
    }


class FakeResearchClient:
    def __init__(self):
        self.calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def search(self, query, limit):
        return {"query": query, "papers": [{"doi": "10.1000/a"}],
                "limit": limit, "provider_status": {"mock": {"status": "OK"}}}

    async def paper(self, doi):
        return {"checked_at": "2026-10-18T00:00:00Z",
                "paper": {"doi": "10.1000/a", "title": "A Test Study"}}

    async def retraction(self, doi):
        return {"doi": doi, "status": "NO_UPDATE_IN_CHECKED_METADATA"}

    async def fulltext(self, pmcid, max_chars=30000):
        return _fulltext()

    async def source_quote(self, pmcid, quote):
        return {"pmcid": pmcid, "quote": quote, "status": "TEXTUAL_MATCH_ONLY"}

    async def find_assets(self, doi):
        return {"doi": doi, "status": "METADATA_ONLY", "links": []}


@pytest.fixture
def offline(monkeypatch):
    monkeypatch.setattr(server, "ResearchClient", FakeResearchClient)


@pytest.mark.asyncio
async def test_search_and_get_paper_wrappers(offline):
    out = await server.search_literature("clinical trial", 5)
    assert out["papers"][0]["doi"] == "10.1000/a"
    assert (await server.get_paper("10.1000/a"))["paper"]["title"] == "A Test Study"


@pytest.mark.asyncio
async def test_citation_validity_is_strictly_bibliographic(offline):
    matched = await server.verify_citation("10.1000/a", "a test study")
    mismatched = await server.verify_citation("10.1000/a", "different claim")
    assert matched["status"] == "BIBLIOGRAPHIC_MATCH"
    assert mismatched["status"] == "TITLE_MISMATCH"
    assert matched["scientific_content_verified"] is False
    with pytest.raises(ValueError):
        await server.verify_citation("10.1000/a", "")


@pytest.mark.asyncio
async def test_retraction_fulltext_and_source_quote(offline):
    assert (await server.check_retraction("10.1000/a"))["status"] == (
        "NO_UPDATE_IN_CHECKED_METADATA")
    full = await server.read_fulltext("PMC1234")
    assert full["pmcid"] == "PMC1234"
    assert (await server.verify_source_quote("PMC1234", "randomized"))[
        "status"] == "TEXTUAL_MATCH_ONLY"


@pytest.mark.asyncio
async def test_direct_pmc_annotation_tool_does_not_infer_bias(offline):
    report = await server.audit_pmc_methodology(
        "PMC1234", "Outcome", "randomized_trial", [{
            "domain": "sequence_generation", "answer": "reported_yes",
            "quote": "assignment was randomized using a published sequence",
        }])
    assert report["source_located_domain_count"] == 1
    assert report["fulltext_origin"] == "EUROPE_PMC_PMC_XML"
    assert report["risk_of_bias_judgement"] == "NOT_ASSESSED"
    assert report["scientific_quality_assessed"] is False


@pytest.mark.asyncio
async def test_data_assets_and_search_log(offline, monkeypatch, tmp_path):
    monkeypatch.setenv("EVIDENCE_LEDGER_PATH", str(tmp_path / "ledger.jsonl"))
    assert (await server.find_data_and_code("10.1000/a"))["links"] == []
    report = await server.log_review_search("quantum", 2)
    assert report["stage"] == "SEARCH_LOG_ONLY"
    assert report["evidence_record"]["status"] == "RECORDED"
    assert server.verify_evidence_ledger()["status"] == "VALID"
    row = await server.export_evidence("review_note", {"id": "test"})
    assert row["entry_number"] == 2
    assert server.verify_evidence_ledger()["count"] == 2


def test_local_structured_wrappers_keep_no_scientific_claim():
    quote = server.verify_claim("randomized", "The study was randomized.", "test")
    assert quote["scientific_claim_verified"] is False
    assert server.assess_methodology(
        "The study was randomized.", "test")["status"] == "SCREENING_ONLY"
    out = server.audit_methodology(
        "example", "endpoint", "randomized_trial",
        "Participants were randomly allocated using envelopes.",
        [{"domain": "sequence_generation", "answer": "reported_yes",
          "quote": "randomly allocated using envelopes"}])
    assert out["scientific_quality_assessed"] is False
    assert server.check_statistical_reporting([
        {"p_value": .05, "sample_size": 32},
    ])["status"] == "NUMERICAL_CONSISTENCY_SCREEN_ONLY"
    assert server.compare_studies([{"doi": "a"}, {"doi": "b"}])[
        "conflict_verdict"] == "NOT_VERIFIED"
    graph = server.build_evidence_graph(
        [{"id": "a"}, {"id": "b"}],
        [{"source": "a", "target": "b", "evidence_id": "doi:10.1000/a"}])
    assert graph["status"] == "USER_SUPPLIED_EDGES_UNVERIFIED"
