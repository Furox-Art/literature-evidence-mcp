"""MCP v2 interface for research primitives.

Deliberately refuses to synthesize scientific truth from bibliographic metadata.
"""
from __future__ import annotations

import os

from mcp.server import MCPServer

from literature_evidence_mcp.core import (
    EvidenceLedger,
    ResearchClient,
    compare_metadata,
    evidence_graph,
    normalize_doi,
    screen_methodology,
    verify_quote,
)
from literature_evidence_mcp.methodology import (
    audit_methodology_evidence,
    audit_statistical_fields,
)

mcp = MCPServer("Literature Evidence MCP")


@mcp.tool()
async def search_literature(query: str, limit_per_source: int = 10) -> dict:
    """Search OpenAlex, Europe PMC, Crossref; deduplicate DOI and report each provider error."""
    async with ResearchClient() as researcher:
        return await researcher.search(query, limit_per_source)


@mcp.tool()
async def get_paper(doi: str) -> dict:
    """Get Crossref DOI metadata and source links; does NOT validate scientific conclusions."""
    async with ResearchClient() as researcher:
        return await researcher.paper(doi)


@mcp.tool()
async def verify_citation(doi: str, claimed_title: str) -> dict:
    """Verify bibliographic DOI/title match in Crossref (not validity of the publication)."""
    if not 1 <= len(claimed_title.strip()) <= 700:
        raise ValueError("Provide a 1–700 character citation title")
    async with ResearchClient() as researcher:
        record = await researcher.paper(doi)
    authoritative_title = record["paper"].get("title") or ""
    compact = lambda v: " ".join(v.casefold().split()).strip(" .")
    equal = compact(authoritative_title) == compact(claimed_title)
    return {"doi": normalize_doi(doi), "status": "BIBLIOGRAPHIC_MATCH" if equal else "TITLE_MISMATCH",
            "claimed_title": claimed_title, "crossref_title": authoritative_title,
            "scientific_content_verified": False, "checked_at": record["checked_at"]}


@mcp.tool()
async def check_retraction(doi: str) -> dict:
    """Inspect Crossref update-to and Retraction Watch-linked updates; absence is inconclusive."""
    async with ResearchClient() as researcher:
        return await researcher.retraction(doi)


@mcp.tool()
async def read_fulltext(pmcid: str, max_chars: int = 30000) -> dict:
    """Read OA full-text XML by PMCID from Europe PMC, with source hash and truncation flag."""
    async with ResearchClient() as researcher:
        return await researcher.fulltext(pmcid, max_chars)


@mcp.tool()
async def verify_source_quote(pmcid: str, quote: str) -> dict:
    """Retrieve Europe PMC full text and locate quote in source paragraphs; NOT a scientific verdict."""
    async with ResearchClient() as researcher:
        return await researcher.source_quote(pmcid, quote)


@mcp.tool()
def verify_claim(quote: str, source_text: str, source_id: str) -> dict:
    """Check literal quote presence. This cannot scientifically verify a claim."""
    return verify_quote(quote, source_text, source_id)


@mcp.tool()
def assess_methodology(source_text: str, source_id: str) -> dict:
    """Transparent phrase screening only; NOT a RoB-2, GRADE, or statistical audit."""
    return screen_methodology(source_text, source_id)


@mcp.tool()
def audit_methodology(
    study_id: str, outcome: str, study_design: str, source_text: str,
    annotations: list[dict],
) -> dict:
    """Audit traceability of outcome-specific, user-annotated methods evidence.

    Quotes are checked against supplied raw text. Labels are never scientifically
    validated. Human RoB2/ROBINS-I assessment remains necessary.
    """
    return audit_methodology_evidence(
        study_id, outcome, study_design, source_text, annotations,
    )


@mcp.tool()
def check_statistical_reporting(records: list[dict]) -> dict:
    """Find mechanically inconsistent p values/CIs/sample-size entries, not test results."""
    return audit_statistical_fields(records)


@mcp.tool()
def compare_studies(papers: list[dict]) -> dict:
    """Compare supplied bibliographic metadata; no inferred theoretical disagreements."""
    return compare_metadata(papers)


@mcp.tool()
async def find_data_and_code(doi: str) -> dict:
    """Find Crossref links to supplements/data/software, if registered; do not fetch them."""
    async with ResearchClient() as researcher:
        return await researcher.find_assets(doi)


@mcp.tool()
def build_evidence_graph(nodes: list[dict], edges: list[dict]) -> dict:
    """Validate user-supplied evidence graph with traceable evidence identifiers."""
    return evidence_graph(nodes, edges)


@mcp.tool()
async def log_review_search(query: str, limit_per_source: int = 10) -> dict:
    """Search + log reproducible search records; NOT an exhaustive systematic review."""
    async with ResearchClient() as researcher:
        result = await researcher.search(query, limit_per_source)
    receipt = await EvidenceLedger().append("review_search", result)
    return {"search": result, "evidence_record": receipt,
            "stage": "SEARCH_LOG_ONLY", "notice": "PRISMA screening/extraction not implemented."}


@mcp.tool()
async def export_evidence(kind: str, payload: dict) -> dict:
    """Append a JSON evidence record to local hash-chained JSONL ledger."""
    return await EvidenceLedger().append(kind, payload)


@mcp.tool()
def verify_evidence_ledger() -> dict:
    """Check local JSONL ledger integrity; cannot detect replacement of the entire ledger."""
    return EvidenceLedger().verify()


def main() -> None:
    transport = os.getenv("MCP_TRANSPORT", "stdio").lower()
    if transport not in {"stdio", "streamable-http"}:
        raise ValueError("MCP_TRANSPORT must be stdio or streamable-http")
    if transport == "streamable-http":
        # Localhost only by default. Do not expose remotely without an auth/reverse proxy.
        mcp.run(transport="streamable-http", host="127.0.0.1", port=int(os.getenv("MCP_PORT", "8000")))
    else:
        mcp.run()


if __name__ == "__main__":
    main()
