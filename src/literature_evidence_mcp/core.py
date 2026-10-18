"""Testable research primitives; no model-generated scientific verdicts.

All external values are untrusted. Provider records are metadata, not evidence of truth.
Network requests are restricted to fixed provider origins and fixed API routes.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx
from filelock import FileLock

from literature_evidence_mcp.methodology import _locate

CROSSREF = "https://api.crossref.org"
OPENALEX = "https://api.openalex.org"
EUROPE_PMC = "https://www.ebi.ac.uk"
DOI_RE = re.compile(r"^10\.\d{4,9}/\S{1,240}$", re.I)
PMCID_RE = re.compile(r"^PMC[0-9]{1,15}$", re.I)
RETR_TYPES = {"retraction", "withdrawal", "removed"}
MAX_QUERY = 600
MAX_TEXT = 30_000


class ProviderError(RuntimeError):
    """A provider failed; explicitly distinguished from no results."""


def normalize_doi(value: str) -> str:
    value = value.strip()
    value = re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:)", "", value, flags=re.I)
    if not DOI_RE.fullmatch(value) or any(c in value for c in "?#\\"):
        raise ValueError("Expected a valid DOI (10.<registrant>/<suffix>)")
    return value.lower()


def _query(value: str) -> str:
    value = value.strip()
    if not 2 <= len(value) <= MAX_QUERY:
        raise ValueError("Query must be 2–600 characters")
    return value


def _limit(value: int, upper: int = 20) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= upper:
        raise ValueError(f"Limit must be an integer from 1 to {upper}")
    return value


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _authors_crossref(record: dict) -> list[str]:
    return [" ".join(p for p in [a.get("given"), a.get("family")] if p)
            for a in record.get("author", [])[:25] if isinstance(a, dict)]


def _as_paper(record: dict, provider: str) -> dict:
    if provider == "crossref":
        title = record.get("title") or []
        dates = record.get("published", {}).get("date-parts", [[]])
        year = dates[0][0] if dates and dates[0] else None
        return {"doi": (record.get("DOI") or "").lower() or None,
                "title": title[0] if isinstance(title, list) and title else None,
                "year": year, "authors": _authors_crossref(record),
                "journal": (record.get("container-title") or [None])[0],
                "source": provider, "url": record.get("URL"), "abstract": None,
                "source_id": record.get("DOI")}
    if provider == "openalex":
        index = record.get("abstract_inverted_index") or {}
        tokens: dict[int, str] = {}
        for word, positions in index.items():
            for p in positions:
                if isinstance(p, int) and 0 <= p < 50_000:
                    tokens[p] = word
        abstract = " ".join(tokens[i] for i in sorted(tokens)) if tokens else None
        return {"doi": ((record.get("doi") or "").removeprefix("https://doi.org/").lower() or None),
                "title": record.get("display_name") or record.get("title"),
                "year": record.get("publication_year"),
                "authors": [x.get("author", {}).get("display_name") for x in record.get("authorships", [])[:25]],
                "journal": (record.get("primary_location") or {}).get("source", {}).get("display_name")
                if (record.get("primary_location") or {}).get("source") else None,
                "source": provider, "url": record.get("id"),
                "abstract": abstract, "source_id": record.get("id")}
    if provider == "europepmc":
        return {"doi": (record.get("doi") or "").lower() or None,
                "title": record.get("title"), "year": record.get("pubYear"),
                "authors": (record.get("authorString") or "").split(", ")[:25],
                "journal": record.get("journalTitle"), "source": provider,
                "url": f"https://europepmc.org/article/{record.get('source', 'MED')}/{record.get('id')}"
                if record.get("id") else None,
                "abstract": None, "source_id": record.get("id"),
                "pmcid": record.get("pmcid")}
    raise ValueError("Unknown source")


class ResearchClient:
    def __init__(self, client: httpx.AsyncClient | None = None):
        self._client = client
        self._owned = client is None

    async def __aenter__(self):
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(15.0), follow_redirects=False,
                headers={"User-Agent": "LiteratureEvidenceMCP/0.3.1 (scholarly-metadata-client)",
                         "Accept": "application/json"},
                limits=httpx.Limits(max_connections=10),
            )
        return self

    async def __aexit__(self, exc_type, exc, tb):
        if self._owned and self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _get(self, base: str, path: str, params: dict | None = None,
                   *, xml: bool = False) -> Any:
        if base not in {CROSSREF, OPENALEX, EUROPE_PMC}:
            raise ValueError("Unapproved provider origin")
        if not path.startswith("/") or ".." in path or path.startswith("//"):
            raise ValueError("Unapproved API path")
        # Provider-specific allowlist prevents server-side arbitrary URL retrieval.
        allowed = {
            CROSSREF: path == "/works" or path.startswith("/works/"),
            OPENALEX: path == "/works" or path.startswith("/works/"),
            EUROPE_PMC: path == "/europepmc/webservices/rest/search" or bool(
                re.fullmatch(r"/europepmc/webservices/rest/PMC[0-9]{1,15}/fullTextXML", path)
            ),
        }
        if not allowed[base]:
            raise ValueError("Unapproved API route")
        if self._client is None:
            raise RuntimeError("Use ResearchClient with async with")
        for attempt in range(3):
            try:
                # Stream and cap bytes before buffering any untrusted provider response.
                # Europe PMC fullTextXML rejects the default JSON Accept header (HTTP 406).
                headers = {"Accept": "application/xml"} if xml else None
                async with self._client.stream(
                    "GET", base + path, params=params, headers=headers,
                ) as response:
                    if response.status_code in {429, 500, 502, 503, 504}:
                        if attempt < 2:
                            await asyncio.sleep(0.2 * (2**attempt))
                        continue  # After the third attempt the loop reports retry exhaustion.
                    response.raise_for_status()
                    cap = 4_000_000 if xml else 2_000_000
                    chunks, total = [], 0
                    async for chunk in response.aiter_bytes():
                        total += len(chunk)
                        if total > cap:
                            raise ProviderError("Provider response is too large")
                        chunks.append(chunk)
                    body = b"".join(chunks)
                    return body if xml else json.loads(body)
            except (httpx.RequestError, httpx.HTTPStatusError, ValueError) as exc:
                if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 404:
                    raise ProviderError("Provider did not find this record") from exc
                raise ProviderError(f"Provider request failed: {type(exc).__name__}") from exc
        raise ProviderError("Provider retry limit reached")

    async def search(self, query: str, limit: int = 10,
                     sources: tuple[str, ...] = ("openalex", "europepmc", "crossref")) -> dict:
        query, limit = _query(query), _limit(limit, 20)
        sources = tuple(dict.fromkeys(sources))
        if not sources or not set(sources) <= {"openalex", "europepmc", "crossref"}:
            raise ValueError("Unsupported literature provider")

        async def one(source: str):
            try:
                if source == "openalex":
                    params = {"search.title_abstract_keywords": query, "per_page": limit}
                    if os.getenv("OPENALEX_API_KEY"):
                        params["api_key"] = os.environ["OPENALEX_API_KEY"]
                    raw = (await self._get(OPENALEX, "/works", params)).get("results", [])
                elif source == "crossref":
                    raw = (await self._get(CROSSREF, "/works", {
                        "query.bibliographic": query, "rows": limit})).get("message", {}).get("items", [])
                else:
                    raw = (await self._get(EUROPE_PMC, "/europepmc/webservices/rest/search", {
                        "query": query, "pageSize": limit, "format": "json"})).get("resultList", {}).get("result", [])
                return source, {"status": "OK", "count": len(raw)}, [_as_paper(x, source) for x in raw]
            except (ProviderError, KeyError, TypeError, AttributeError, ValueError) as exc:
                return source, {"status": "ERROR", "error": str(exc)}, []

        collected = await asyncio.gather(*(one(source) for source in sources))
        dedup: dict[str, dict] = {}
        provider_status: dict[str, dict] = {}
        for source, status, papers in collected:
            provider_status[source] = status
            for paper in papers:
                key = paper.get("doi") or f"{source}:{paper.get('source_id') or paper.get('title')}"
                if key not in dedup:
                    dedup[key] = {**paper, "sources": [source]}
                else:
                    dedup[key]["sources"].append(source)
                    for field in ("title", "abstract", "year", "journal"):
                        if not dedup[key].get(field) and paper.get(field):
                            dedup[key][field] = paper[field]
        return {"query": query, "checked_at": _utcnow(), "provider_status": provider_status,
                "papers": list(dedup.values()), "coverage": "NON_EXHAUSTIVE",
                "notice": "Search coverage and record freshness vary; absence is not proof of nonexistence."}

    async def paper(self, doi: str) -> dict:
        doi = normalize_doi(doi)
        crossref = await self._get(CROSSREF, "/works/" + quote(doi, safe=""))
        return {"checked_at": _utcnow(), "paper": _as_paper(crossref["message"], "crossref"),
                "raw_fields": {"type": crossref["message"].get("type"),
                               "relation": crossref["message"].get("relation", {}),
                               "update_to": crossref["message"].get("update-to", []),
                               "license": crossref["message"].get("license", []),
                               "link": crossref["message"].get("link", [])},
                "status": "METADATA_RETRIEVED_NOT_CONTENT_VERIFIED"}

    async def retraction(self, doi: str) -> dict:
        doi = normalize_doi(doi)
        try:
            item = (await self._get(CROSSREF, "/works/" + quote(doi, safe="")))["message"]
        except ProviderError as exc:
            return {"doi": doi, "status": "NOT_VERIFIED", "error": str(exc),
                    "checked_at": _utcnow(), "provider": "crossref"}
        updates = item.get("update-to") or []
        normalized = [{"type": x.get("type"), "doi": x.get("DOI"),
                       "source": x.get("source"), "date": x.get("updated", {}).get("date-parts")}
                      for x in updates if isinstance(x, dict)]
        retracts = [x for x in normalized if str(x.get("type", "")).lower() in RETR_TYPES]
        status = ("RETRACTION_REPORTED" if retracts else
                  "UPDATE_REPORTED" if normalized else "NO_UPDATE_IN_CHECKED_METADATA")
        return {"doi": doi, "status": status, "updates": normalized,
                "checked_at": _utcnow(), "provider": "crossref",
                "notice": "Absence in Crossref metadata does not establish that a paper is unretracted."}

    async def find_assets(self, doi: str) -> dict:
        metadata = await self.paper(doi)
        raw = metadata["raw_fields"]
        links = [{"url": x.get("URL"), "content_type": x.get("content-type")}
                 for x in raw["link"] if isinstance(x, dict) and x.get("URL")]
        relations = {k: v for k, v in raw["relation"].items()
                     if any(term in k.lower() for term in ("dataset", "software", "supplement", "version"))}
        return {"doi": normalize_doi(doi), "status": "METADATA_ONLY",
                "links": links, "relations": relations,
                "notice": "Links are unverified publisher metadata and may require licensing/access."}

    async def fulltext(self, pmcid: str, max_chars: int = MAX_TEXT) -> dict:
        pmcid = pmcid.strip().upper()
        if not PMCID_RE.fullmatch(pmcid):
            raise ValueError("Expected PMCID such as PMC123456")
        max_chars = _limit(max_chars, MAX_TEXT)
        import defusedxml.ElementTree as ET  # only used when this optional route is requested
        raw = await self._get(EUROPE_PMC,
                              f"/europepmc/webservices/rest/{pmcid}/fullTextXML", xml=True)
        root = ET.fromstring(raw)
        title = " ".join(root.findtext(".//article-title", default="").split())
        # Preserve a stable, source-addressable section/paragraph location for each quote.
        # JATS sections may nest. Iterate paragraphs once to prevent double counting.
        segments = []
        body = root.find(".//body")
        if body is not None:
            parents = {child: parent for parent in body.iter() for child in parent}
            for paragraph in body.iter("p"):
                paragraph_text = " ".join("".join(paragraph.itertext()).split())
                if not paragraph_text:
                    continue
                # Walk the JATS tree using parent lookup; do not fabricate PDF page numbers.
                current = paragraph
                section = None
                while current in parents:
                    current = parents[current]
                    if current.tag == "sec":
                        section = current
                        break
                sec_title = (" ".join("".join(section.find("title").itertext()).split())
                             if section is not None and section.find("title") is not None
                             else "Unsectioned body")
                index = len(segments) + 1
                segments.append({"span_id": f"{pmcid}:p{index}", "section": sec_title,
                                 "paragraph_index": index, "text": paragraph_text,
                                 "sha256_text": hashlib.sha256(paragraph_text.encode()).hexdigest()})
        joined, spans = "", []
        for segment in segments:
            chunk = ("\n\n" if joined else "") + segment["section"] + ": " + segment["text"]
            if len(joined) + len(chunk) > max_chars:
                break
            begin = len(joined) + len("\n\n" if joined else "") + len(segment["section"]) + 2
            joined += chunk
            spans.append({**segment, "offset_start": begin,
                          "offset_end": begin + len(segment["text"])})
        return {"pmcid": pmcid, "title": title, "content": joined,
                "truncated": len(spans) != len(segments), "spans": spans,
                "paragraph_count": len(segments),
                "status": "FULLTEXT_ACCESSED_NOT_SCIENTIFICALLY_VERIFIED",
                "sha256_xml": hashlib.sha256(raw).hexdigest(), "checked_at": _utcnow(),
                "notice": "Each pN identifies a paragraph in this retrieved XML only, not a PDF page."
                          " Source rights and scientific conclusions remain unverified."}

    async def source_quote(self, pmcid: str, quote_text: str) -> dict:
        if not (1 <= len(quote_text.strip()) <= 1000):
            raise ValueError("Quote length must be 1–1000 characters")
        full = await self.fulltext(pmcid)
        matches = []
        for item in full["spans"]:
            span = _locate(item["text"], quote_text)
            if span is not None:
                matches.append({"span_id": item["span_id"], "section": item["section"],
                                "paragraph_index": item["paragraph_index"],
                                "sha256_text": item["sha256_text"],
                                "offset_start": span[0], "offset_end": span[1]})
        status = ("TEXTUAL_MATCH_ONLY" if matches else
                  "NOT_VERIFIED_SOURCE_TRUNCATED" if full["truncated"] else "NOT_VERIFIED")
        return {"pmcid": full["pmcid"], "quote": quote_text,
                "status": status,
                "matched_spans": matches, "xml_sha256": full["sha256_xml"],
                "retrieval_truncated": full["truncated"],
                "scientific_claim_verified": False,
                "notice": "Matching a direct source passage does not establish scientific validity."
                          " No match is inconclusive if retrieval was truncated."}


def verify_quote(quote_text: str, source_text: str, source_id: str) -> dict:
    """Verifies only literal textual presence; never scientific validity."""
    if not (1 <= len(quote_text.strip()) <= 1000):
        raise ValueError("Quote length must be 1–1000 characters")
    if not (1 <= len(source_text) <= 250_000):
        raise ValueError("Source text length must be 1–250000 characters")
    if not (1 <= len(source_id.strip()) <= 300):
        raise ValueError("Source identifier required")
    span = _locate(source_text, quote_text)
    exact = span is not None
    return {"source_id": source_id, "quote": quote_text, "text_match": exact,
            "offset_start": span[0] if span else None,
            "offset_end": span[1] if span else None,
            "status": "TEXTUAL_MATCH_ONLY" if exact else "NOT_VERIFIED",
            "scientific_claim_verified": False,
            "source_text_sha256": hashlib.sha256(source_text.encode()).hexdigest(),
            "notice": "Text occurrence neither establishes causality nor replicates results."}


DESIGN_HINTS = {
    "randomization": [r"\brandomi[sz]ed\b", r"\brandom assignment\b"],
    "blinding": [r"\bdouble.blind\b", r"\bsingle.blind\b", r"\bblinded\b"],
    "power_analysis": [r"\bpower analysis\b", r"\bsample size calculation\b"],
    "preregistration": [r"\bpreregister", r"\bpre.register", r"\bregistered report\b"],
    "multiple_testing": [r"\bbonferroni\b", r"\bfalse discovery rate\b", r"\bfdr correction\b"],
    "confidence_intervals": [r"\bconfidence interval", r"\b95% ci\b"],
    "data_availability": [r"\bdata availability\b", r"\bdata are available\b"],
}


def screen_methodology(text: str, source_id: str) -> dict:
    if not 1 <= len(text) <= 250_000 or not source_id.strip():
        raise ValueError("Nonempty source text and source identifier are required")
    hits = {}
    for field, patterns in DESIGN_HINTS.items():
        found = []
        for pattern in patterns:
            match = re.search(pattern, text, re.I)
            if match:
                found.append({"snippet": text[max(0, match.start() - 70):match.end() + 70],
                              "offset": match.start()})
        hits[field] = {"status": "TERM_MENTIONED" if found else "NOT_ASSESSED", "examples": found}
    return {"source_id": source_id, "status": "SCREENING_ONLY",
            "scientific_quality_assessed": False, "features": hits,
            "notice": "Keyword detection is not a valid risk-of-bias or methods-quality assessment."
                      " A non-match does not mean a method was not used."}


def compare_metadata(papers: list[dict]) -> dict:
    if not 2 <= len(papers) <= 20:
        raise ValueError("Provide between 2 and 20 papers")
    return {"status": "METADATA_COMPARISON_ONLY", "study_count": len(papers),
            "records": [{k: p.get(k) for k in ("doi", "title", "year", "source")}
                        for p in papers], "conflict_verdict": "NOT_VERIFIED",
            "notice": "A difference in metadata is not evidence of scientific contradiction."}


def evidence_graph(nodes: list[dict], edges: list[dict]) -> dict:
    if len(nodes) > 250 or len(edges) > 500:
        raise ValueError("Graph exceeds v0.1 safety limits")
    ids = [n.get("id") for n in nodes]
    if any(not isinstance(n, str) or not n.strip() for n in ids) or len(ids) != len(set(ids)):
        raise ValueError("Node IDs must be unique nonempty strings")
    for e in edges:
        if e.get("source") not in ids or e.get("target") not in ids:
            raise ValueError("Edges must reference existing nodes")
        if not e.get("evidence_id"):
            raise ValueError("Edges need explicit evidence_id; never infer links")
    return {"nodes": nodes, "edges": edges, "status": "USER_SUPPLIED_EDGES_UNVERIFIED",
            "notice": "Edges are stored as assertions, not independently verified scientific facts."}


class EvidenceLedger:
    """Append-only hash-chained JSONL; no tamper-proof claims against file replacement."""

    def __init__(self, file: str | Path | None = None):
        self.file = Path(file or os.getenv("EVIDENCE_LEDGER_PATH", "evidence-ledger.jsonl"))
        self._lock_path = str(self.file) + ".lock"

    @staticmethod
    def _hash(entry: dict) -> str:
        data = json.dumps(entry, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(data.encode()).hexdigest()

    def verify(self) -> dict:
        prev, count = "0" * 64, 0
        if not self.file.exists():
            return {"status": "VALID_EMPTY", "count": 0, "head": prev}
        try:
            with self.file.open(encoding="utf-8") as file:
                for line in file:
                    record = json.loads(line)
                    digest = record.pop("entry_hash")
                    if record.get("previous_hash") != prev or self._hash(record) != digest:
                        return {"status": "TAMPER_DETECTED", "line": count + 1}
                    prev, count = digest, count + 1
        except (OSError, ValueError, KeyError, TypeError):
            return {"status": "TAMPER_OR_CORRUPTION_DETECTED", "line": count + 1}
        return {"status": "VALID", "count": count, "head": prev}

    async def append(self, kind: str, payload: dict) -> dict:
        if not isinstance(kind, str) or not re.fullmatch(r"[a-z_]{2,48}", kind):
            raise ValueError("Invalid evidence type")
        if not isinstance(payload, dict):
            raise ValueError("Evidence payload must be an object")
        encoded = json.dumps(payload, ensure_ascii=False, allow_nan=False)
        if len(encoded.encode()) > 100_000:
            raise ValueError("Evidence payload exceeds limit")
        return await asyncio.to_thread(self._append_locked, kind, payload)

    def _append_locked(self, kind: str, payload: dict) -> dict:
        self.file.parent.mkdir(parents=True, exist_ok=True)
        # FileLock synchronizes independent tool calls, processes and server instances.
        with FileLock(self._lock_path, timeout=15):
            check = self.verify()
            if check["status"] not in ("VALID", "VALID_EMPTY"):
                raise ValueError("Refusing to append to corrupt ledger")
            entry = {"schema": "evidence-ledger-v1", "kind": kind,
                     "timestamp": _utcnow(), "previous_hash": check["head"], "payload": payload}
            entry["entry_hash"] = self._hash(entry)
            with self.file.open("a", encoding="utf-8") as file:
                file.write(json.dumps(entry, sort_keys=True, ensure_ascii=False) + "\n")
                file.flush()
                os.fsync(file.fileno())
            return {"status": "RECORDED", "hash": entry["entry_hash"],
                    "entry_number": check["count"] + 1, "path": str(self.file)}
