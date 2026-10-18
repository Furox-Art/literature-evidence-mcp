"""EvidenceBench COLM'25 test: aspect recall at k; lexical baselines vs abstention.

Original annotations include human-expert validation of LLM-produced evidence
labels; this is not a manually re-annotated expert gold test. No test tuning.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
from pathlib import Path

try:
    from .scifact_gold import containment, jaccard
except ImportError:  # Direct execution through python scripts/evaluation/evidencebench_gold.py
    from scifact_gold import containment, jaccard

from literature_evidence_mcp.core import verify_quote

URL = ("https://raw.githubusercontent.com/EvidenceBench/EvidenceBench/"
       "bf1d9633c694381c7b016fd56ee9f95f48593cc3/"
       "datasets/evidencebench_test_set.json")
DATA_SHA256 = "771cc068e3e79764c2eb523e7d0d9fb276d00254a99212c73c1137674b49d18b"
COMMIT = "bf1d9633c694381c7b016fd56ee9f95f48593cc3"


def aspect_recall(row, selected, results_only=False):
    valid = row["results_aspect_list_ids"] if results_only else row["aspect_list_ids"]
    if not valid:
        return None
    aspect2sentence = row["aspect2sentence_indices"]
    hits = sum(bool(set(aspect2sentence[aspect]) & set(selected)) for aspect in valid)
    return hits / len(valid)


def evaluate(input_file):
    if hashlib.sha256(input_file.read_bytes()).hexdigest() != DATA_SHA256:
        raise ValueError("EvidenceBench test data SHA mismatch")
    source = json.loads(input_file.read_text())
    if not isinstance(source, dict) or len(source) != 293:
        raise ValueError("Unexpected EvidenceBench test partition size")
    from rank_bm25 import BM25Okapi
    methods = ("jaccard", "claim_word_coverage", "third_party_rank_bm25",
               "first_k", "uniform_random", "existing_mcp_literal_claim_proxy",
               "gold_oracle_reference_not_a_competitor")
    outcomes = {method: {"all_aspect_at_10": [], "results_aspect_at_5": []}
                for method in methods}
    anchors = {"tested": 0, "found": 0}
    sizes = []
    for paper_id, row in sorted(source.items()):
        sentences = row["paper_as_candidate_pool"]
        if not sentences or not row["aspect_list_ids"]:
            raise ValueError("Missing candidate sentences or aspect annotations")
        sizes.append(len(sentences))
        hypothesis = row["hypothesis"]
        indexed = list(range(len(sentences)))
        jrank = sorted(indexed, key=lambda i: (-jaccard(hypothesis, sentences[i]), i))
        crank = sorted(indexed, key=lambda i: (-containment(hypothesis, sentences[i]), i))
        import re
        tokenize_sequence = lambda text: re.findall(r"(?u)\b\w\w+\b", text.casefold())
        bm25 = BM25Okapi([tokenize_sequence(sentence) for sentence in sentences])
        bm_scores = bm25.get_scores(tokenize_sequence(hypothesis))
        bmrank = sorted(indexed, key=lambda i: (-float(bm_scores[i]), i))
        seed = int(hashlib.sha256(paper_id.encode()).hexdigest()[:12], 16)
        random_rank = indexed[:]
        random.Random(seed).shuffle(random_rank)
        exact = [i for i, sentence in enumerate(sentences)
                 if len(hypothesis.strip()) <= 1000 and
                 verify_quote(hypothesis, sentence, paper_id)["text_match"]]
        oracle = row["evidence_retrieval_at_optimal_evaluation"]["one_selection_of_sentences"]
        results_oracle = (row["results_evidence_retrieval_at_5_evaluation"] or {}).get(
            "one_selection_of_sentences", [])
        choices = {"jaccard":jrank, "claim_word_coverage":crank,
                   "third_party_rank_bm25":bmrank,
                   "first_k":indexed, "uniform_random":random_rank,
                   "existing_mcp_literal_claim_proxy":exact,
                   "gold_oracle_reference_not_a_competitor":oracle}
        gold = oracle
        joined = " ".join(sentences)
        for gold_index in gold:
            sentence = sentences[gold_index]
            if 1 <= len(sentence.strip()) <= 1000 and len(joined) < 250000:
                anchors["tested"] += 1
                anchors["found"] += verify_quote(sentence, joined, paper_id)["text_match"]
        for name, ranking in choices.items():
            for label, k, results_only in (
                ("all_aspect_at_10",10,False), ("results_aspect_at_5",5,True)):
                chosen = (results_oracle if results_only else oracle) if name == (
                    "gold_oracle_reference_not_a_competitor") else ranking[:k]
                value = aspect_recall(row, chosen, results_only)
                if value is not None:
                    outcomes[name][label].append(value)
    results = {}
    rng = random.Random(20261018)
    for method, metrics in outcomes.items():
        results[method] = {}
        for key, values in metrics.items():
            n = len(values)
            mean = sum(values) / n if n else None
            intervals = []
            if n:
                for _ in range(500):
                    sample = rng.choices(values, k=n)
                    intervals.append(sum(sample)/n)
                intervals.sort()
            results[method][key] = {
                "evaluated_papers":n, "macro_recall":mean,
                "paper_bootstrap_95pct": [intervals[12], intervals[487]] if n else None,
            }
    return {
        "status": "EVIDENCEBENCH_EXTERNAL_ANNOTATION_TEST_COMPLETED",
        "dataset": "EvidenceBench (Wang et al., COLM 2025)",
        "url":URL, "source_commit":COMMIT, "test_sha256":DATA_SHA256,
        "license":"CC BY (original test subset); train/dev are CC-BY-NC-SA",
        "gold_label_provenance":"LLM-assisted annotation with separate human expert quality checks",
        "split":"original EvidenceBench TEST; no parameter tuning or training",
        "papers":len(source), "candidate_sentences_total":sum(sizes),
        "rankers":results,
        "external_baseline": {"name": "rank-bm25", "version": "0.2.2",
                              "algorithm": "BM25Okapi local sentence ranking",
                              "label_access": False, "same_hypothesis_and_candidates": True},
        "oracle_sentence_literal_trace":anchors,
        "task":"macro aspect recall at 10 and results-aspect recall at 5",
        "limitations":[
            "EvidenceBench gold aspects are LLM-assisted, not entirely manually labeled.",
            "Quote auditor does not rank or retrieve from a hypothesis; abstention is expected.",
            "Exact hypothesis matching is a proxy; not scientific claim classification.",
            "rank-bm25 is an independent retrieval library, NOT a full scientific verification competitor.",
            "Additional BM25 comparator added after preliminary test inspection: exploratory, not preregistered.",
            "First-k and random are controls; oracle selections use gold labels, NOT a comparator.",
            "Aspect recall is NOT scientific factual entailment or risk-of-bias accuracy.",
        ],
    }


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--data", type=Path, required=True)
    a.add_argument("--output", type=Path, required=True)
    args = a.parse_args()
    result = evaluate(args.data)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True)+"\n")
    print("EvidenceBench test papers",result["papers"],
          "annotated gold anchor",result["oracle_sentence_literal_trace"])
    for key, row in result["rankers"].items():
        print(key, "Recall@10",round(row["all_aspect_at_10"]["macro_recall"],5),
              "ResultsRecall@5",round(row["results_aspect_at_5"]["macro_recall"],5))


if __name__ == "__main__":
    main()
