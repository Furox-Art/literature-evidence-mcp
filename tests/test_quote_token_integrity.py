"""Regression cases where textual overlap must not become scientific evidence."""

import hashlib

import httpx
import pytest

from literature_evidence_mcp.core import ResearchClient, verify_quote
from literature_evidence_mcp.methodology import _locate, audit_methodology_evidence
from literature_evidence_mcp.source_audit import audit_pmc_paragraph_evidence


def test_false_positive_with_negated_or_longer_token():
    assert _locate("The trial was insignificant.", "significant") is None
    assert _locate("The treatment was ineffective.", "effective") is None
    assert _locate("The results were not insignificant.", "insignificant") is not None
    assert verify_quote("significant", "The result was insignificant", "p1")[
        "status"] == "NOT_VERIFIED"
    assert verify_quote("effective", "The intervention was ineffective", "p1")[
        "text_match"] is False


def test_source_offsets_exact_case_and_whitespace():
    source = "A RANDOMIZED\n  trial included participants."
    matched = verify_quote("randomized trial", source, "paper-X")
    assert matched["status"] == "TEXTUAL_MATCH_ONLY"
    assert source[matched["offset_start"]:matched["offset_end"]] == "RANDOMIZED\n  trial"
    no_match = verify_quote("participants had a response", source, "paper-X")
    assert no_match["offset_start"] is None
    assert no_match["offset_end"] is None


def test_punctuation_quote_still_matches_without_false_boundaries():
    text = "Treatment arm: (N = 20), with a null result."
    assert _locate(text, "(N = 20)") is not None
    assert _locate(text, "N = 20)") is not None
    assert _locate(text, "(N = 20") is not None
    assert _locate(text, "20") is not None
    assert _locate(text, "2") is None


def test_methodology_annotations_do_not_support_partial_words():
    source = "The reduction was insignificant."
    report = audit_methodology_evidence(
        "example", "effect", "randomized_trial", source,
        [{"domain": "outcome_measurement", "answer": "reported_yes",
          "quote": "reduction was significant."}],
    )
    assert report["untraceable_domain_count"] == 1
    assert report["scientific_quality_assessed"] is False


@pytest.mark.asyncio
async def test_primary_jats_quote_offsets_and_truncation_disambiguation():
    xml = b"""<article><body><sec><title>Results</title>
    <p>The treatment was ineffective in this group.</p>
    <p>A statistically significant change occurred for the other group.</p>
    </sec></body></article>"""
    async with (httpx.AsyncClient(transport=httpx.MockTransport(
        lambda _: httpx.Response(200, content=xml))) as http,
        ResearchClient(http) as client):
        bad = await client.source_quote("PMC75", "effective")
        assert bad["status"] == "NOT_VERIFIED"
        good = await client.source_quote("PMC75", "statistically significant change")
        assert good["status"] == "TEXTUAL_MATCH_ONLY"
        assert len(good["matched_spans"]) == 1
        assert good["matched_spans"][0]["span_id"] == "PMC75:p2"
        full = await client.fulltext("PMC75")
        a = good["matched_spans"][0]
        paragraph = full["spans"][1]["text"]
        assert paragraph[a["offset_start"]:a["offset_end"]] == "statistically significant change"
        assert good["xml_sha256"] == hashlib.sha256(xml).hexdigest()
        truncated = await client.fulltext("PMC75", max_chars=55)
        assert truncated["truncated"] is True
        # The source was truncated, so a missing quote is NOT an absence finding.
        incomplete = audit_pmc_paragraph_evidence(
            truncated, "effect", "randomized_trial",
            [{"domain": "outcome_measurement", "answer": "reported_yes",
              "quote": "statistically significant change"}],
        )
        assert incomplete["domains"]["outcome_measurement"]["status"] == (
            "NOT_VERIFIED_SOURCE_TRUNCATED")
        truncated_result = await client.source_quote("PMC75", "not reported anywhere")
        assert truncated_result["status"] == "NOT_VERIFIED"


@pytest.mark.asyncio
async def test_missing_quote_in_partially_retrieved_xml_reports_incomplete_source(monkeypatch):
    async def incomplete_fulltext(self, pmcid, max_chars=30000):
        return {"pmcid": pmcid, "spans": [], "sha256_xml": "0" * 64,
                "truncated": True}

    monkeypatch.setattr(ResearchClient, "fulltext", incomplete_fulltext)
    async with ResearchClient() as client:
        result = await client.source_quote("PMC75", "statistically significant")
    assert result["status"] == "NOT_VERIFIED_SOURCE_TRUNCATED"
    assert result["retrieval_truncated"] is True
    assert result["matched_spans"] == []
    assert result["scientific_claim_verified"] is False


@pytest.mark.asyncio
async def test_fulltext_content_negotiation_uses_xml_accept_header():
    xml = b"<article><body><sec><title>Methods</title><p>Trial data are reported.</p></sec></body></article>"
    accepts = []

    def provider(request):
        accepts.append(request.headers["accept"])
        if request.headers["accept"] != "application/xml":
            return httpx.Response(406, json={"error": "Not Acceptable"})
        return httpx.Response(200, content=xml, headers={"content-type": "application/xml"})

    async with (httpx.AsyncClient(transport=httpx.MockTransport(provider),
                                  headers={"Accept": "application/json"}) as http,
                ResearchClient(http) as client):
        fulltext = await client.fulltext("PMC75")
    assert accepts == ["application/xml"]
    assert fulltext["paragraph_count"] == 1
    assert fulltext["spans"][0]["section"] == "Methods"
