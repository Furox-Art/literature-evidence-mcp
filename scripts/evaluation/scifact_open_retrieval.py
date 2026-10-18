"""Frozen SciFact *open-corpus* retrieval experiment. No semantic judgment.

Rank all 5,183 SciFact title/abstract records per labeled development claim.
Gold-positive document labels are INCOMPLETE across the full corpus; report
only known-positive recall/MRR, NOT corpus precision or false-positive rate.
No DEV gold is used in ranking or hyperparameter selection.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import random
import re

from rank_bm25 import BM25Okapi

HASHES = {
    "corpus.jsonl": "b8d6c89624cb2ed74dee8938effc4f5d8bd2086887880af8110d64be4ceade62",
    "claims_dev.jsonl": "86f0435d08fdb65d1aa41d1472684f57e6e71930626497bdf4d7a9ec1a632217",
    "claims_train.jsonl": "f4c8fa82d8bd0653a9cc8d61a6ea48c25eacea64e90af5dbf390ebb1b74372f0",
}
TOKEN = re.compile(r"(?u)\b\w\w+\b")
CUTOFFS = (1, 5, 10, 20)


def tokenize(value: str) -> list[str]:
    return TOKEN.findall(value.casefold())


def metrics(ranked: list[int], gold: set[int]) -> dict[str, float]:
    if not gold:
        raise ValueError("Known gold-positive documents required")
    if len(set(ranked)) != len(ranked):
        raise ValueError("Repeated ranked document")
    positions = {doc: rank for rank, doc in enumerate(ranked)}
    answers = {
        f"known_gold_recall_at_{k}": sum(positions.get(doc, len(ranked)) < k for doc in gold) / len(gold)
        for k in CUTOFFS
    }
    gold_ranks = sorted(positions[doc] for doc in gold if doc in positions)
    answers["mrr_first_known_positive"] = 1.0 / (gold_ranks[0] + 1) if gold_ranks else 0.0
    actual = sum(1 / math.log2(rank + 2) for rank in gold_ranks if rank < 10)
    ideal = sum(1 / math.log2(rank + 2) for rank in range(min(10, len(gold))))
    answers["known_gold_ndcg_at_10"] = actual / ideal if ideal else 0.0
    return answers


def percentile_interval(values: list[float]) -> list[float]:
    s = sorted(values)
    return [round(s[int(.025 * len(s))], 5), round(s[int(.975 * len(s))], 5)]


def paired_difference(rows: list[dict], first: str, second: str, field: str) -> dict:
    rng = random.Random(20261018)
    n = len(rows)
    if not n:
        raise ValueError("No labeled queries")
    diffs = [r[first][field] - r[second][field] for r in rows]
    boot = [sum(rng.choices(diffs, k=n)) / n for _ in range(500)]
    return {"mean": sum(diffs) / n,
            "paired_query_bootstrap_95pct": percentile_interval(boot)}


def evaluate(folder: Path) -> dict:
    for file, wanted in HASHES.items():
        if hashlib.sha256((folder / file).read_bytes()).hexdigest() != wanted:
            raise ValueError("SciFact snapshot SHA-256 mismatch: " + file)
    papers = [json.loads(s) for s in (folder / "corpus.jsonl").read_text().splitlines() if s]
    claims = [json.loads(s) for s in (folder / "claims_dev.jsonl").read_text().splitlines() if s]
    ids = [p["doc_id"] for p in papers]
    if len(ids) != 5183 or len(ids) != len(set(ids)) or len(claims) != 300:
        raise ValueError("Unexpected SciFact corpus/DEV partition")
    doc_tokens = [tokenize(p["title"] + " " + " ".join(p["abstract"])) for p in papers]
    doc_sets = [set(words) for words in doc_tokens]
    scorer = BM25Okapi(doc_tokens)
    rows = []
    zero_gold = 0
    for claim in claims:
        gold = {int(k) for k, rationales in claim["evidence"].items() if rationales}
        if not gold:
            zero_gold += 1
            continue
        if not gold <= set(ids):
            raise ValueError("Gold paper absent from corpus")
        words = tokenize(claim["claim"])
        needle = set(words)
        bm25 = [float(score) for score in scorer.get_scores(words)]
        jaccard = [len(needle & doc) / len(needle | doc) if needle | doc else 0.0
                   for doc in doc_sets]
        containment = [len(needle & doc) / len(needle) if needle else 0.0
                       for doc in doc_sets]
        scores = {"bm25": bm25, "jaccard": jaccard, "claim_word_coverage": containment}
        evaluated = {"claim_id": claim["id"]}
        for method, vals in scores.items():
            order = sorted(range(len(ids)), key=lambda ix: (-vals[ix], ids[ix]))
            evaluated[method] = metrics([ids[ix] for ix in order], gold)
        evaluated["corpus_id_order_control"] = metrics(sorted(ids), gold)
        rows.append(evaluated)
    methods = ("bm25", "jaccard", "claim_word_coverage", "corpus_id_order_control")
    fields = (tuple(f"known_gold_recall_at_{k}" for k in CUTOFFS) +
              ("mrr_first_known_positive", "known_gold_ndcg_at_10"))
    aggregate = {}
    for method in methods:
        aggregate[method] = {}
        for field in fields:
            scores = [r[method][field] for r in rows]
            rng = random.Random(20261018)
            bootstrap = [sum(rng.choices(scores, k=len(scores))) / len(scores) for _ in range(500)]
            aggregate[method][field] = {
                "macro_mean": sum(scores) / len(scores),
                "query_bootstrap_95pct": percentile_interval(bootstrap),
            }
    return {
        "status": "OPEN_CORPUS_RETRIEVAL_BENCHMARK_COMPLETE_LIMITED_GOLD",
        "dataset": "SciFact public DEV; titles/abstracts from official corpus",
        "data_sha256": HASHES,
        "source_archive_sha256": "11c621288d41ac144d29b13b0f8503b3820b7d6e8b1f6ff24dff335c196d76be",
        "documents_ranked_per_query": len(ids),
        "dev_queries": len(claims),
        "queries_with_known_gold_positive": len(rows),
        "queries_without_annotated_gold_positive": zero_gold,
        "label_based_tuning": False,
        "retrieval_methods": aggregate,
        "paired_bm25_minus_jaccard_recall_at_10": paired_difference(
            rows, "bm25", "jaccard", "known_gold_recall_at_10"),
        "paired_bm25_minus_word_coverage_recall_at_10": paired_difference(
            rows, "bm25", "claim_word_coverage", "known_gold_recall_at_10"),
        "current_mcp_native_open_corpus_retriever": False,
        "current_mcp_open_corpus_recall": None,
        "claim_support_or_contradict_accuracy": None,
        "limitations": [
            "Corpus-wide relevance judgments are incomplete, therefore no precision/FPR is reported.",
            "Queries with zero known positive evidence are excluded from recall denominators.",
            "Only preexisting external BM25/lexical rankers evaluated; not an MCP retrieval feature.",
            "Ranked full 5183-paper SciFact corpus, not just cited candidates.",
            "No DEV threshold/model tuning, no semantic entailment or risk-of-bias assessment.",
            "Confidence intervals are query bootstrap variation, not clinical validation.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = evaluate(args.data)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n")
    print("SCIFACT_OPEN_CORPUS_RESULTS " + json.dumps({
        "documents": result["documents_ranked_per_query"],
        "gold_queries": result["queries_with_known_gold_positive"],
        "zero_gold_queries": result["queries_without_annotated_gold_positive"],
        "recall_at_10": {name: d["known_gold_recall_at_10"] for name, d
                         in result["retrieval_methods"].items()},
        "paired_bm25_minus_jaccard": result["paired_bm25_minus_jaccard_recall_at_10"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
