"""Direct-source methodology traceability regression tests."""
import hashlib

import httpx
import pytest

from literature_evidence_mcp.core import ResearchClient
from literature_evidence_mcp.source_audit import audit_pmc_paragraph_evidence


def source_fixture(truncated=False):
    entries = [
        {"span_id": "PMC123:p1", "section": "Methods", "paragraph_index": 1,
         "text": "Study participants were randomly assigned in the laboratory."},
        {"span_id": "PMC123:p2", "section": "Results", "paragraph_index": 2,
         "text": "The outcome analysis was prespecified in the protocol."},
    ]
    for x in entries:
        x["sha256_text"] = hashlib.sha256(x["text"].encode()).hexdigest()
    return {"pmcid": "PMC123", "sha256_xml": "1" * 64,
            "spans": entries, "truncated": truncated}


def assessment(quote, domain="sequence_generation", answer="reported_yes"):
    return {"domain": domain, "answer": answer, "quote": quote}


def audit(fulltext, annotations):
    return audit_pmc_paragraph_evidence(
        fulltext, "Primary outcome", "randomized_trial", annotations,
    )


def test_direct_source_anchor_section_hash_and_offsets():
    quote = "participants were randomly assigned"
    out = audit(source_fixture(), [assessment(quote)])
    row = out["domains"]["sequence_generation"]["annotations"][0]
    assert out["fulltext_origin"] == "EUROPE_PMC_PMC_XML"
    assert out["xml_sha256"] == "1" * 64
    assert len(row["matched_paragraphs"]) == 1
    match = row["matched_paragraphs"][0]
    assert match["span_id"] == "PMC123:p1"
    assert match["section"] == "Methods"
    assert source_fixture()["spans"][0]["text"][
        match["offset_start"]:match["offset_end"]] == quote
    assert out["scientific_quality_assessed"] is False
    assert out["risk_of_bias_judgement"] == "NOT_ASSESSED"


def test_absence_from_complete_article_requires_review():
    out = audit(source_fixture(), [assessment("Participants were blinded centrally.")])
    assert out["domains"]["sequence_generation"]["status"] == (
        "UNTRACEABLE_ANNOTATION_REVIEW_REQUIRED")
    assert out["untraceable_domain_count"] == 1


def test_truncated_source_cannot_establish_absence():
    out = audit(source_fixture(truncated=True),
                [assessment("Participants were blinded centrally.")])
    assert out["domains"]["sequence_generation"]["status"] == (
        "NOT_VERIFIED_SOURCE_TRUNCATED")
    assert out["retrieval_truncated"] is True
    assert out["risk_of_bias_judgement"] == "NOT_ASSESSED"


def test_cross_paragraph_combined_quote_never_counts():
    out = audit(source_fixture(), [assessment(
        "in the laboratory. The outcome analysis was prespecified")])
    assert out["source_located_domain_count"] == 0
    assert out["untraceable_domain_count"] == 1


def test_no_match_from_section_title():
    out = audit(source_fixture(), [assessment(
        "Methods", answer="unclear")])
    assert not out["domains"]["sequence_generation"]["annotations"][0][
        "source_match"]


def test_same_paragraph_conflicting_annotation_not_auto_decided():
    quote = "Study participants were randomly assigned in the laboratory."
    out = audit(source_fixture(), [assessment(quote, answer="reported_yes"),
                                  assessment(quote, answer="reported_no")])
    assert out["contradictory_domain_count"] == 1


def test_integrity_check_before_source_audit():
    fulltext = source_fixture()
    fulltext["spans"][0]["text"] = "Manipulated text"
    with pytest.raises(ValueError, match="hash mismatch"):
        audit(fulltext, [])


@pytest.mark.asyncio
async def test_extracted_primary_xml_to_source_bound_audit():
    xml = b"""<article><body><sec><title>Methods</title>
      <p>Study participants were randomly assigned in the laboratory.</p>
      <p>The outcome analysis was prespecified in the protocol.</p>
      </sec></body></article>"""
    async with (httpx.AsyncClient(transport=httpx.MockTransport(
        lambda _: httpx.Response(200, content=xml))) as client,
        ResearchClient(client) as researcher):
        direct = await researcher.fulltext("PMC123")
    out = audit(direct, [assessment("participants were randomly assigned")])
    assert out["xml_sha256"] == hashlib.sha256(xml).hexdigest()
    assert out["source_located_domain_count"] == 1
