"""Opt-in, user-supplied-corpus BM25 retrieval. Never a scientific verdict.

This module makes no network requests and does not mutate the scientific core.
"""
from __future__ import annotations

import hashlib
import importlib
import math
import re

TOKEN = re.compile(r"(?u)\b\w\w+\b")


def rank_supplied_evidence(query: str, documents: list[dict], top_k: int = 10) -> dict:
    """Rank titles/abstracts with BM25Okapi, returning only lexically matched candidates."""
    if not isinstance(query, str) or not 2 <= len(query.strip()) <= 1000:
        raise ValueError("query must have 2-1000 characters")
    if type(top_k) is not int or not 1 <= top_k <= 50:
        raise ValueError("top_k must be an integer from 1 to 50")
    if not isinstance(documents, list) or not 1 <= len(documents) <= 10000:
        raise ValueError("documents must contain 1-10000 candidate records")

    prepared = []
    used_ids: set[str] = set()
    total_size = 0
    for document in documents:
        if not isinstance(document, dict):
            raise TypeError("each document must be an object")
        raw_id = document.get("id")
        if type(raw_id) is int:
            identifier = str(raw_id)
        elif isinstance(raw_id, str):
            identifier = raw_id.strip()
        else:
            raise ValueError("each document requires a string or integer id")
        if not 1 <= len(identifier) <= 256:
            raise ValueError("document id must have 1-256 characters")
        if identifier in used_ids:
            raise ValueError("document ids must be unique")
        used_ids.add(identifier)
        title = document.get("title", "")
        abstract = document.get("abstract", "")
        if not isinstance(title, str) or not isinstance(abstract, str):
            raise TypeError("title and abstract must be strings")
        if len(title) > 700 or len(abstract) > 20000 or not (title.strip() or abstract.strip()):
            raise ValueError("nonempty title or abstract required, within size bounds")
        total_size += len(title.encode("utf-8")) + len(abstract.encode("utf-8"))
        if total_size > 8_000_000:
            raise ValueError("total candidate text exceeds 8MB")
        words = TOKEN.findall((title + " " + abstract).casefold())
        prepared.append((identifier, title, abstract, words))

    query_words = TOKEN.findall(query.casefold())
    if not query_words:
        raise ValueError("query has no indexable words of two or more characters")
    unique_query_words = set(query_words)
    corpus = [row[3] for row in prepared]
    if not any(corpus):
        return {
            "status": "NO_INDEXABLE_DOCUMENT_TEXT", "candidate_count": len(prepared),
            "lexically_matched_candidates": 0, "results": [],
            "semantic_support_verified": False, "source_authenticity_verified": False,
        }

    try:
        bm25 = importlib.import_module("rank_bm25")
    except ModuleNotFoundError as exc:
        if exc.name != "rank_bm25":
            raise
        return {
            "status": "OPTIONAL_BM25_NOT_INSTALLED", "backend": "BM25Okapi",
            "install_extra": "literature-evidence-mcp[retrieval]",
            "candidate_count": len(prepared), "results": [],
            "semantic_support_verified": False, "source_authenticity_verified": False,
        }

    scores = bm25.BM25Okapi(corpus).get_scores(query_words)
    matched = [index for index, words in enumerate(corpus)
               if unique_query_words.intersection(words)]
    for index in matched:
        if not math.isfinite(float(scores[index])):
            raise ValueError("BM25 returned non-finite scores")
    ranked = sorted(matched, key=lambda index: (-float(scores[index]), prepared[index][0]))
    results = []
    for rank, index in enumerate(ranked[:top_k], start=1):
        identifier, title, abstract, _ = prepared[index]
        results.append({
            "rank": rank, "id": identifier, "title": title,
            "abstract_preview": abstract[:300],
            "bm25_score": float(scores[index]),
            "supplied_text_sha256": hashlib.sha256(
                (title + "\n" + abstract).encode("utf-8")).hexdigest(),
            "source_authenticity_verified": False,
            "scientific_support_verified": False,
        })

    return {
        "status": "BM25_LEXICAL_CANDIDATES_ONLY" if matched else "NO_QUERY_TERM_OVERLAP",
        "backend": "rank-bm25 0.2.2 / BM25Okapi",
        "candidate_count": len(prepared),
        "lexically_matched_candidates": len(matched),
        "returned_count": len(results), "results": results,
        "semantic_support_verified": False,
        "source_authenticity_verified": False,
        "scientific_methodology_assessed": False,
        "notice": "Ranks only caller-supplied titles/abstracts; no API search, "
                  "full-text retrieval, source authentication, entailment or scientific verdict.",
    }
