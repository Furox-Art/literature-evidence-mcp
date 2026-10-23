"""SciFact full-corpus interface parity check, not a scientific accuracy metric."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

from rank_bm25 import BM25Okapi

from literature_evidence_mcp.bm25_retrieval import rank_supplied_evidence
from scripts.evaluation.scifact_open_retrieval import HASHES

TOKEN = re.compile(r"(?u)\b\w\w+\b")


def validate(folder: Path) -> dict:
    for name, expected in HASHES.items():
        if hashlib.sha256((folder / name).read_bytes()).hexdigest() != expected:
            raise ValueError("SciFact dataset hash mismatch: " + name)
    papers = [json.loads(line) for line in (folder / "corpus.jsonl").read_text().splitlines() if line]
    claims = [json.loads(line) for line in (folder / "claims_dev.jsonl").read_text().splitlines() if line]
    documents = [{"id": item["doc_id"], "title": item["title"],
                  "abstract": " ".join(item["abstract"])} for item in papers]
    words = [TOKEN.findall((row["title"] + " " + row["abstract"]).casefold())
             for row in documents]
    sets = [set(row) for row in words]
    model = BM25Okapi(words)
    verified_queries = 0
    for row in claims:
        if not row["evidence"]:
            continue
        query_tokens = TOKEN.findall(row["claim"].casefold())
        query_set = set(query_tokens)
        scores = model.get_scores(query_tokens)
        matched = [i for i, doc_set in enumerate(sets) if query_set.intersection(doc_set)]
        ids = [str(p["id"]) for p in documents]
        independent_order = sorted(matched, key=lambda i: (-float(scores[i]), ids[i]))
        expected = [ids[i] for i in independent_order[:10]]
        actual = rank_supplied_evidence(row["claim"], documents, 10)
        if [hit["id"] for hit in actual["results"]] != expected:
            raise AssertionError("BM25 MCP and reference ranks differ")
        if actual["semantic_support_verified"] or actual["source_authenticity_verified"]:
            raise AssertionError("Lexical retrieval cannot certify a scientific claim")
        verified_queries += 1
        if verified_queries == 6:
            break
    if verified_queries != 6:
        raise AssertionError("Insufficient SciFact test claims")
    return {"status": "EXTERNAL_CORPUS_INTERFACE_PARITY_PASS",
            "documents_per_query": len(documents), "evaluated_queries": verified_queries,
            "semantic_science_accuracy": None}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(validate(args.data), sort_keys=True))


if __name__ == "__main__":
    main()
