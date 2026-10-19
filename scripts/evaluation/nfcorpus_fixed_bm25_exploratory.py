"""Exploratory fixed-corpus NFCorpus BM25 evaluation, not live API search.

Reuses the production opt-in BM25Okapi tokenization, default parameters and
lexical-match filtering. Reads public BEIR test judgments only on explicit
execution; produces aggregate-only metrics and no winner declaration.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from collections import defaultdict
from pathlib import Path

from literature_evidence_mcp.bm25_retrieval import TOKEN
from scripts.evaluation.pin_dual_track_candidate_sources import CANDIDATES

K = (1, 5, 10)
EXPECTED_DOCS = 3633
EXPECTED_TEST_QUERIES = 323


def load_nfcorpus(path: Path) -> tuple[list[dict], dict[str, str], dict[str, set[str]], int]:
    if hashlib.sha256(path.read_bytes()).hexdigest() != CANDIDATES["retrieval"]["sha256"]:
        raise ValueError("NFCorpus archive SHA-256 mismatch")
    with zipfile.ZipFile(path) as z:
        documents = [json.loads(x) for x in
                     z.read("nfcorpus/corpus.jsonl").decode("utf-8").splitlines() if x]
        queries = [json.loads(x) for x in
                   z.read("nfcorpus/queries.jsonl").decode("utf-8").splitlines() if x]
        qrels = z.read("nfcorpus/qrels/test.tsv").decode("utf-8").splitlines()
    ids = [row["_id"] for row in documents]
    if len(ids) != len(set(ids)) or len(ids) != EXPECTED_DOCS:
        raise ValueError("Unexpected or duplicated corpus IDs")
    by_query = {row["_id"]: row["text"] for row in queries}
    if len(by_query) != len(queries):
        raise ValueError("Duplicated query IDs")
    if not qrels or qrels[0].split("\t") != ["query-id", "corpus-id", "score"]:
        raise ValueError("Unexpected NFCorpus qrels header")
    relevance: dict[str, set[str]] = defaultdict(set)
    observed = set()
    for line in qrels[1:]:
        parts = line.split("\t")
        if len(parts) != 3:
            raise ValueError("Malformed relevance triple")
        query, doc, score = parts
        if query not in by_query or doc not in ids or (query, doc) in observed:
            raise ValueError("Unknown or duplicate test judgment")
        observed.add((query, doc))
        if int(score) > 0:
            relevance[query].add(doc)
        else:
            relevance[query] |= set()
    if len(relevance) != EXPECTED_TEST_QUERIES:
        raise ValueError("Unexpected test query count")
    return documents, by_query, dict(relevance), len(observed)


def score_documents(
    documents: list[dict], queries: dict[str, str], gold: dict[str, set[str]],
) -> dict:
    from rank_bm25 import BM25Okapi

    texts = [
        (str(doc.get("title") or "") + " " + str(doc.get("text") or "")).casefold()
        for doc in documents
    ]
    ids = [doc["_id"] for doc in documents]
    tokens = [TOKEN.findall(x) for x in texts]
    if not all(tokens):
        raise ValueError("Empty tokenized source document")
    index = BM25Okapi(tokens)
    inverted: dict[str, set[int]] = defaultdict(set)
    for pos, parts in enumerate(tokens):
        for word in set(parts):
            inverted[word].add(pos)

    recalls = {k: [] for k in K}
    mrr = []
    no_overlap = 0
    without_positives = 0
    for qid in sorted(gold):
        query_tokens = TOKEN.findall(queries[qid].casefold())
        if not query_tokens:
            raise ValueError("NFCorpus test query has no indexable words")
        candidates = set()
        for word in query_tokens:
            candidates.update(inverted.get(word, ()))
        if not candidates:
            no_overlap += 1
        scores = index.get_scores(query_tokens)
        top = sorted(candidates, key=lambda pos: (-float(scores[pos]), ids[pos]))[:10]
        ranked = [ids[pos] for pos in top]
        positive = gold[qid]
        if not positive:
            without_positives += 1
            continue
        for k in K:
            recalls[k].append(len(set(ranked[:k]) & positive) / len(positive))
        mrr.append(next((1 / (pos + 1) for pos, doc in enumerate(ranked)
                         if doc in positive), 0.0))
    if not mrr:
        raise ValueError("No known-positive queries can be evaluated")
    return {
        "status": "EXPLORATORY_FIXED_CORPUS_RETRIEVAL_NOT_COMPETITOR_COMPARISON",
        "dataset": "BEIR NFCorpus public test",
        "fixed_corpus_documents": len(documents),
        "test_queries": len(gold),
        "scored_queries": len(mrr),
        "no_known_positive_queries": without_positives,
        "no_lexical_match_queries": no_overlap,
        "known_positive_recall_at_k": {str(k): sum(v) / len(v) for k, v in recalls.items()},
        "mrr_at_10": sum(mrr) / len(mrr),
        "backend": "rank-bm25 0.2.2 BM25Okapi (production default tokenization)",
        "candidate_filter": "At least one exact query-token overlap",
        "document_title_body_concat": True,
        "comparison": "single pre-existing project implementation; no external system executed",
        "precision_at_k": None,
        "precision_unavailable_reason": "Incomplete corpus-level negative relevance judgments",
        "scientific_superiority_demonstrated": False,
        "limitations": [
            "Public retrospective qrels, not independent prospective gold.",
            "Fixed-corpus ranking is not live literature-provider search.",
            "Only positive relevance scores counted as known positives.",
            "MRR uses top-10 returned lexical matches; absent hit is zero.",
            "No competitor executed on the same documents and queries.",
            "No patient-facing or medical evidence truth is assessed.",
        ],
    }


def evaluate(source: Path) -> dict:
    docs, queries, relevant, judged = load_nfcorpus(source)
    result = score_documents(docs, queries, relevant)
    result["qrels_rows_inspected"] = judged
    result["archive_sha256"] = CANDIDATES["retrieval"]["sha256"]
    return result


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--dataset", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    result = evaluate(args.dataset)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n")
    print("NFCORPUS_EXPLORATORY_DONE", result["scored_queries"],
          "recall@10", round(result["known_positive_recall_at_k"]["10"], 5))


if __name__ == "__main__":
    main()
