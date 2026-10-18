"""Opt-in fourth bibliographic source; never infer relevance or scientific truth."""
from __future__ import annotations

import asyncio

from literature_evidence_mcp.core import (
    SEMANTIC_SCHOLAR,
    ProviderError,
    ResearchClient,
    _limit,
    _query,
    _utcnow,
    normalize_doi,
)


def _s2_paper(item: dict) -> dict:
    if not isinstance(item, dict):
        raise TypeError("Malformed Semantic Scholar paper")
    ids = item.get("externalIds") or {}
    if not isinstance(ids, dict):
        raise TypeError("Malformed Semantic Scholar identifiers")
    raw_doi = ids.get("DOI")
    doi = None
    status = "MISSING"
    if raw_doi is not None:
        try:
            doi = normalize_doi(raw_doi)
        except (ValueError, TypeError, AttributeError):
            status = "INVALID_PROVIDER_DOI_NOT_RESOLVED"
        else:
            status = "SYNTAX_VALID_NOT_RESOLVED"
    authors = item.get("authors") or []
    if not isinstance(authors, list):
        raise TypeError("Malformed Semantic Scholar authors")
    return {
        "doi": doi,
        "doi_raw": raw_doi if status == "INVALID_PROVIDER_DOI_NOT_RESOLVED" else None,
        "doi_status": status,
        "title": item.get("title"),
        "year": item.get("year"),
        "authors": [x.get("name") for x in authors[:25] if isinstance(x, dict)],
        "journal": item.get("venue"),
        "abstract": item.get("abstract"),
        "url": item.get("url"),
        "source": "semantic_scholar",
        "source_id": item.get("paperId"),
        "citation_count_provider_reported": item.get("citationCount"),
    }


async def search_four_providers(query: str, limit_per_source: int = 10) -> dict:
    """Concurrently obtain 3 existing sources + optional S2, with isolated errors.

    DOI equality merges only syntactically valid IDs. Conflicting metadata is
    preserved; DOI-less records are never joined by title or S2 score.
    """
    query, limit_per_source = _query(query), _limit(limit_per_source, 20)
    async with ResearchClient() as client:
        async def s2() -> tuple[dict, list[dict]]:
            try:
                raw = await client._get(
                    SEMANTIC_SCHOLAR, "/graph/v1/paper/search", {
                        "query": query, "limit": limit_per_source,
                        "fields": "title,year,authors,venue,externalIds,abstract,url,citationCount",
                    },
                )
                rows = raw["data"]
                if not isinstance(rows, list):
                    raise TypeError("Semantic Scholar non-list data")
                records = [_s2_paper(row) for row in rows]
                return {"status": "OK", "count": len(records)}, records
            except (ProviderError, ValueError, KeyError, TypeError, AttributeError) as exc:
                rate_limited = isinstance(exc, ProviderError) and "(HTTP 429)" in str(exc)
                return {"status": "RATE_LIMITED" if rate_limited else "ERROR",
                        "error": str(exc)}, []

        original, (status, additional) = await asyncio.gather(
            client.search(query, limit_per_source), s2()
        )
    original["provider_status"]["semantic_scholar"] = status
    seen = {p["doi"]: p for p in original["papers"] if p.get("doi")}
    for paper in additional:
        doi = paper["doi"]
        if doi and doi in seen:
            existing = seen[doi]
            existing["sources"].append("semantic_scholar")
            for field in ("title", "year", "journal"):
                old, new = existing.get(field), paper.get(field)
                if not old and new:
                    existing[field] = new
                    existing["metadata_field_sources"][field] = "semantic_scholar"
                elif old and new and str(old).strip().casefold() != str(new).strip().casefold():
                    existing["metadata_disagreements"].append({
                        "field": field,
                        "chosen_source": existing["metadata_field_sources"].get(field),
                        "chosen_value": old,
                        "other_source": "semantic_scholar",
                        "other_value": new,
                        "status": "REVIEW_REQUIRED_NOT_RESOLVED",
                    })
        else:
            paper["sources"] = ["semantic_scholar"]
            paper["metadata_field_sources"] = {
                field: "semantic_scholar" for field in ("title", "year", "journal")
                if paper.get(field)
            }
            paper["metadata_disagreements"] = []
            original["papers"].append(paper)
            if doi:
                seen[doi] = paper
    original["mode"] = "FOUR_PROVIDER_METADATA_SEARCH_NOT_VERIFIED"
    original["checked_at"] = _utcnow()
    original["coverage"] = "NON_EXHAUSTIVE"
    original["scientific_quality_assessed"] = False
    original["notice"] = (
        "S2 may rate-limit unauthenticated requests. Provider errors and DOI "
        "disagreements remain explicit; provider ranking is not an expert relevance test."
    )
    return original
