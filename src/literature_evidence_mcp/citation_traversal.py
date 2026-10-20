"""Conservative, bounded forward/backward OpenAlex citation traversal.

Edges are *provider-asserted bibliographic links*, not independent citation,
methodology, relevance or scientific-content verification.
"""
from __future__ import annotations

import re
from urllib.parse import quote

from literature_evidence_mcp.core import (
    OPENALEX,
    ProviderError,
    ResearchClient,
    _limit,
    _utcnow,
    normalize_doi,
)

WORK = re.compile(r"W[0-9]{1,15}")

_REQUEST_LIMIT = 12


class _RequestBudgetExhausted(Exception):
    """Raised when the traversal has spent its twelve-request budget."""


def _work_id(record: object) -> str | None:
    if not isinstance(record, str):
        return None
    ident = record.removeprefix("https://openalex.org/")
    return ident if WORK.fullmatch(ident) else None


def _node(raw: dict) -> dict:
    ident = _work_id(raw.get("id"))
    if not ident:
        raise ValueError("Missing valid OpenAlex work identifier")
    input_doi = raw.get("doi")
    doi, status = None, "MISSING"
    if input_doi:
        try:
            doi = normalize_doi(input_doi)
        except (ValueError, TypeError, AttributeError):
            status = "INVALID_PROVIDER_DOI"
        else:
            status = "SYNTAX_VALID_NOT_RESOLVED"
    return {
        "id": ident, "title": raw.get("display_name"),
        "doi": doi, "doi_status": status,
        "year": raw.get("publication_year"),
        "source": "openalex", "source_id": raw.get("id"),
        "citation_count_provider_reported": raw.get("cited_by_count"),
        "scientific_content_verified": False,
    }


async def traverse_citations(
    seed_doi: str, max_depth: int = 1, max_per_direction: int = 5,
    directions: str = "both",
) -> dict:
    """BFS at most 2 levels, 12 network requests, 30 nodes. No relevance scoring."""
    doi = normalize_doi(seed_doi)
    if isinstance(max_depth, bool) or not isinstance(max_depth, int) or max_depth not in (1, 2):
        raise ValueError("max_depth must be 1 or 2")
    max_per_direction = _limit(max_per_direction, 10)
    if directions not in {"forward", "backward", "both"}:
        raise ValueError("directions must be forward, backward or both")
    nodes: dict[str, dict] = {}
    edges: dict[tuple[str, str], dict] = {}
    errors: list[dict] = []
    incomplete = False
    requests = 0
    queue: list[str] = []
    async with ResearchClient() as client:
        async def fetch(path: str, params: dict | None = None) -> dict:
            nonlocal requests
            if requests >= _REQUEST_LIMIT:
                raise _RequestBudgetExhausted
            requests += 1
            return await client._get(OPENALEX, path, params)

        try:
            root = await fetch("/works/https://doi.org/" + quote(doi, safe="/"))
            if not isinstance(root, dict):
                raise TypeError("OpenAlex root was not a record")
            root_node = _node(root)
        except (ValueError, ProviderError, TypeError, KeyError) as exc:
            return {
                "seed_doi": doi, "status": "BLOCKED_SEED_LOOKUP",
                "nodes": [], "edges": [], "provider_errors": [str(exc)],
                "checked_at": _utcnow(), "coverage": "NON_EXHAUSTIVE",
                "scientific_content_verified": False,
            }
        # A DOI lookup returning an unrelated or DOI-less record is not a
        # verified seed identity. Do not traverse a potentially different paper.
        if root_node["doi"] != doi:
            return {
                "seed_doi": doi, "status": "BLOCKED_SEED_IDENTITY_NOT_VERIFIED",
                "nodes": [], "edges": [],
                "provider_errors": [{
                    "provider": "openalex", "reason": "SEED_DOI_MISSING_OR_MISMATCH",
                    "requested_doi": doi, "provider_doi": root_node["doi"],
                    "source_id": root_node["source_id"],
                }],
                "checked_at": _utcnow(), "coverage": "NON_EXHAUSTIVE",
                "scientific_content_verified": False,
            }
        root_id = root_node["id"]
        nodes[root_id] = root_node
        cache: dict[str, dict] = {root_id: root}
        queue.append(root_id)

        for level in range(1, max_depth + 1):
            next_queue: list[str] = []
            for current in queue:
                if requests >= 12 or len(nodes) >= 30:
                    incomplete = True
                    break
                # Every queued work was cached at insertion; never refetch it.
                data = cache[current]
                if directions in ("backward", "both"):
                    listed = data.get("referenced_works") or []
                    if not isinstance(listed, list):
                        errors.append({"work": current, "relation": "references",
                                       "error": "Provider references were not a list"})
                        incomplete = True
                        listed = []
                    selected = [_work_id(i) for i in listed]
                    ids = list(dict.fromkeys(x for x in selected if x))
                    if len(ids) > max_per_direction:
                        incomplete = True
                    ids = ids[:max_per_direction]
                    if ids:
                        try:
                            batch = await fetch("/works", {
                                "filter": "openalex:" + "|".join(ids), "per_page": len(ids)
                            })
                            papers = batch["results"]
                            if not isinstance(papers, list):
                                raise TypeError("References result was not a list")
                            fetched = {_work_id(p.get("id")): p for p in papers if isinstance(p, dict)}
                            for ref in ids:
                                target = fetched.get(ref)
                                if target is None:
                                    incomplete = True
                                    continue
                                if ref not in nodes and len(nodes) >= 30:
                                    incomplete = True
                                    break
                                if ref not in nodes:
                                    nodes[ref] = _node(target)
                                    cache[ref] = target
                                    next_queue.append(ref)
                                edges[(current, ref)] = {
                                    "source": current, "target": ref,
                                    "relation": "CITES_PROVIDER_ASSERTED",
                                    "evidence_source": "openalex.referenced_works",
                                    "observed_at_depth": level,
                                }
                        except (ProviderError, ValueError, TypeError, KeyError) as exc:
                            errors.append({"work": current, "relation": "references",
                                           "error": str(exc)})
                            incomplete = True
                if directions in ("forward", "both"):
                    try:
                        incoming = await fetch("/works", {
                            "filter": "cites:" + current, "per_page": max_per_direction
                        })
                        papers = incoming["results"]
                        if not isinstance(papers, list):
                            raise TypeError("Citation result was not a list")
                        meta = incoming.get("meta") or {}
                        if (isinstance(meta, dict) and isinstance(meta.get("count"), int)
                                and meta["count"] > len(papers)):
                            incomplete = True
                        for citing in papers:
                            if not isinstance(citing, dict):
                                incomplete = True
                                continue
                            source = _work_id(citing.get("id"))
                            if not source:
                                incomplete = True
                                continue
                            if source not in nodes and len(nodes) >= 30:
                                incomplete = True
                                break
                            if source not in nodes:
                                nodes[source] = _node(citing)
                                cache[source] = citing
                                next_queue.append(source)
                            edges[(source, current)] = {
                                "source": source, "target": current,
                                "relation": "CITES_PROVIDER_ASSERTED",
                                "evidence_source": "openalex.filter.cites",
                                "observed_at_depth": level,
                            }
                    except _RequestBudgetExhausted:
                        incomplete = True
                        break
                    except (ProviderError, ValueError, TypeError, KeyError) as exc:
                        errors.append({"work": current, "relation": "citations",
                                       "error": str(exc)})
                        incomplete = True
            queue = next_queue
    return {
        "seed_doi": doi, "seed_work": root_id,
        "status": "PARTIAL" if incomplete or errors else "PROVIDER_METADATA_RETRIEVED",
        "nodes": list(nodes.values()), "edges": list(edges.values()),
        "provider_errors": errors, "requested_depth": max_depth,
        "requested_directions": directions,
        "requests_used": requests, "request_limit": 12, "node_limit": 30,
        "checked_at": _utcnow(),
        "coverage": "NON_EXHAUSTIVE_ONE_PAGE_PER_DIRECTION",
        "scientific_content_verified": False,
        "notice": (
            "No ranking or subject relevance assessment. OpenAlex asserted citation edges "
            "only; DOI syntax is not work identity verification. No absence claim from "
            "partial, missing or rate-limited provider results."
        ),
    }
