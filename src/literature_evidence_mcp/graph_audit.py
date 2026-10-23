"""Trace citation consequences of supplied, source-attributed publication notices.

Alerts never convert a citing paper into a retracted paper.
"""
from __future__ import annotations

import asyncio
from collections import deque


def publication_alerts(nodes: list[dict], edges: list[dict], notices: list[dict]) -> dict:
    if not all(isinstance(x, list) for x in (nodes, edges, notices)):
        raise TypeError("Input collections must be lists")
    if len(nodes) > 10000 or len(edges) > 50000 or len(notices) > 10000:
        raise ValueError("Graph too large")
    ids: set[str] = set()
    for n in nodes:
        nid = n.get("id") if isinstance(n, dict) else None
        if not isinstance(nid, str) or not nid or nid in ids:
            raise ValueError("Nodes require distinct IDs")
        ids.add(nid)
    graph: dict[str, list[tuple[str, str]]] = {nid: [] for nid in ids}
    for edge in edges:
        if not isinstance(edge, dict):
            raise TypeError("Edges must be objects")
        cited, citing, source = edge.get("cited_id"), edge.get("citing_id"), edge.get("source_id")
        if (not isinstance(cited, str) or cited not in ids
                or not isinstance(citing, str) or citing not in ids
                or not isinstance(source, str) or not source):
            raise ValueError("Known paper IDs and edge evidence required")
        graph[cited].append((citing, source))
    alerts = []
    for notice in notices:
        if not isinstance(notice, dict):
            raise TypeError("Notices must be objects")
        root = notice.get("paper_id")
        if (not isinstance(root, str) or root not in ids
                or notice.get("kind") not in {"retraction", "correction", "expression_of_concern"}):
            raise ValueError("Notice kind/target invalid")
        source = notice.get("source_id")
        if not isinstance(source, str) or not source:
            raise ValueError("Notice source required")
        seen = {root}
        pending: deque[tuple[str, list[str]]] = deque([(root, [])])
        while pending:
            current, chain = pending.popleft()
            alerts.append({"paper_id": current, "source_notice_paper": root,
                           "notice_kind": notice["kind"], "source_id": source,
                           "citation_evidence_chain": chain,
                           "status": "DIRECT_NOTICE" if not chain else "CITING_PAPER_REVIEW_ALERT_ONLY"})
            for nxt, evidence in graph[current]:
                if nxt not in seen:
                    seen.add(nxt)
                    pending.append((nxt, chain + [evidence]))
    return {"status": "SOURCE_ATTRIBUTED_ALERTS", "alerts": alerts,
            "notice": "Citation descendants are NOT retracted; metadata edges and notices require independent validation."}


async def crossref_notice_chain(dois: list[str], edges: list[dict]) -> dict:
    """Fetch Crossref updates, then propagate REVIEW alerts along supplied edges.

    A missing metadata update is not evidence of no retraction.
    """
    from literature_evidence_mcp.core import ResearchClient, normalize_doi

    if not isinstance(dois, list) or not 1 <= len(dois) <= 40:
        raise ValueError("1-40 paper DOIs required")
    normalized = [normalize_doi(x) for x in dois]
    if len(set(normalized)) != len(normalized):
        raise ValueError("Duplicate DOIs")
    uncertain = []
    notices = []
    async with ResearchClient() as client:
        # Independent lookups run concurrently; a slow provider no longer
        # multiplies the wall-clock cost by the number of supplied DOIs.
        rows = await asyncio.gather(*(client.retraction(doi) for doi in normalized))
    for doi, row in zip(normalized, rows, strict=True):
        if row["status"] == "NOT_VERIFIED":
            uncertain.append(doi)
        # A notice points at its target with "update-to"; the cited work points
        # back at the notice with "updated-by". Only the latter concerns this DOI.
        for update in row.get("updated_by", []):
            kind = str(update.get("type") or "").lower()
            if "retract" in kind:
                notice_kind = "retraction"
            elif "concern" in kind:
                notice_kind = "expression_of_concern"
            elif kind in {"correction", "corrigendum", "erratum"}:
                notice_kind = "correction"
            else:
                continue
            notices.append({
                "paper_id": doi, "kind": notice_kind,
                "source_id": "crossref:" + doi,
            })
    propagation = publication_alerts([{"id": doi} for doi in normalized], edges, notices)
    return {**propagation, "provider": "crossref", "unverified_dois": uncertain,
            "status": "CROSSREF_NOTICE_METADATA_WITH_UNVERIFIED_GRAPH_LINKS"}
