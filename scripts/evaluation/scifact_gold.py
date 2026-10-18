"""External annotated SciFact train/dev audit; no claim entailment inferred."""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
from collections import Counter, defaultdict
from pathlib import Path

from literature_evidence_mcp.core import verify_quote

URL = "https://scifact.s3-us-west-2.amazonaws.com/release/latest/data.tar.gz"
ARCHIVE_SHA256 = "11c621288d41ac144d29b13b0f8503b3820b7d6e8b1f6ff24dff335c196d76be"


def load(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pairs(claims, docs):
    rows = []
    for claim in claims:
        ids = set(claim["cited_doc_ids"]) | {int(key) for key in claim["evidence"]}
        for did in sorted(ids):
            if did not in docs:
                raise ValueError("Annotated document missing")
            rows.append((claim["id"], did, claim["claim"],
                         " ".join(docs[did]["abstract"]),
                         str(did) in claim["evidence"] and bool(claim["evidence"][str(did)])))
    return rows


def tokens(text):
    return set(re.findall(r"(?u)\b\w\w+\b", text.casefold()))


def jaccard(claim, abstract):
    a, b = tokens(claim), tokens(abstract)
    return len(a & b) / len(a | b) if a | b else 0.0


def containment(claim, abstract):
    a, b = tokens(claim), tokens(abstract)
    return len(a & b) / len(a) if a else 0.0


def confusion(gold, pred):
    if len(gold) != len(pred):
        raise ValueError("mismatched lengths")
    tp = sum(g and p for g, p in zip(gold, pred))
    fp = sum(not g and p for g, p in zip(gold, pred))
    fn = sum(g and not p for g, p in zip(gold, pred))
    tn = sum(not g and not p for g, p in zip(gold, pred))
    return {"tp":tp, "fp":fp, "fn":fn, "tn":tn,
            "precision":tp/(tp+fp) if tp+fp else None,
            "recall":tp/(tp+fn) if tp+fn else None,
            "specificity":tn/(tn+fp) if tn+fp else None,
            "f1":2*tp/(2*tp+fp+fn) if tp else 0.0}


def optimize_train(train, scorer):
    scored = [(scorer(row[2], row[3]), row[4]) for row in train]
    best = (-1.0, 1.01)
    for i in range(101):
        cutoff = i / 100
        metric = confusion([y for _, y in scored],
                           [s >= cutoff for s, _ in scored])["f1"]
        best = max(best, (metric, cutoff))
    return best[1], best[0]


def cluster_ci(claim_ids, gold, pred, repeats=500):
    groups = defaultdict(list)
    for idx, cid in enumerate(claim_ids):
        groups[cid].append(idx)
    ids = sorted(groups)
    if not ids:
        return []
    rng = random.Random(20261018)
    results = []
    for _ in range(repeats):
        ix = [j for cid in rng.choices(ids, k=len(ids)) for j in groups[cid]]
        results.append(confusion([gold[j] for j in ix],
                                 [pred[j] for j in ix])["f1"])
    results.sort()
    return [round(results[int(repeats * p)], 5) for p in (.025, .975)]


def evaluate(folder):
    names = ["corpus.jsonl", "claims_train.jsonl", "claims_dev.jsonl"]
    hashes = {n: sha(folder/n) for n in names}
    source = load(folder/names[0])
    docs = {r["doc_id"]:r for r in source}
    if len(docs) != len(source):
        raise ValueError("duplicate source IDs")
    train_claims, dev_claims = load(folder/names[1]), load(folder/names[2])
    train, dev = pairs(train_claims, docs), pairs(dev_claims, docs)
    gold = [bool(r[4]) for r in dev]
    ids = [r[0] for r in dev]
    scores = {}
    for name, scorer in [("jaccard", jaccard), ("claim_word_coverage", containment)]:
        cut, train_f1 = optimize_train(train, scorer)
        pred = [scorer(r[2], r[3]) >= cut for r in dev]
        metric = confusion(gold, pred)
        metric["claim_cluster_bootstrap_f1_95pct"] = cluster_ci(ids, gold, pred)
        scores[name] = {"train_only_cutoff":cut, "train_f1":train_f1, "dev":metric}
    actual = [verify_quote(row[2], row[3], str(row[1])) for row in dev]
    pred = [row["text_match"] for row in actual]
    metric = confusion(gold, pred)
    metric["claim_cluster_bootstrap_f1_95pct"] = cluster_ci(ids, gold, pred)
    assert all(row["scientific_claim_verified"] is False for row in actual)
    scores["existing_mcp_literal_claim_proxy"] = {
        "dev":metric, "scientific_support_contradict_predictions":0,
        "scientific_label_accuracy":None}
    positive = negative = changed = total = 0
    for claim in dev_claims:
        for docid, rationales in claim["evidence"].items():
            did = int(docid)
            full = " ".join(docs[did]["abstract"])
            for rat in rationales:
                for pos in rat["sentences"]:
                    quote = docs[did]["abstract"][pos]
                    if not 1 <= len(quote.strip()) <= 1000:
                        continue
                    total += 1
                    positive += verify_quote(quote, full, str(did))["text_match"]
                    altered = "  ".join(quote.upper().split())
                    changed += verify_quote(altered, full, str(did))["text_match"]
                    other_ids = sorted(docs)
                    other = other_ids[(other_ids.index(did)+71) % len(other_ids)]
                    negative += verify_quote(quote, " ".join(docs[other]["abstract"]),
                                             str(other))["text_match"]
    labels = Counter(r["label"] for c in dev_claims
                     for rs in c["evidence"].values() for r in rs)
    return {"status":"EVALUATED_LIMITED_SCOPE",
            "dataset":"SciFact (Wadden et al., 2020)",
            "dataset_url":URL, "archive_sha256":ARCHIVE_SHA256,
            "source_commit":"68b98a56d93e0f9da0d2aab4e6c3294699a0f72e",
            "data_file_sha256":hashes,
            "license":"CC-BY-4.0 evidence annotations; ODC-By-1.0 abstracts",
            "gold_split":"train thresholds, untouched dev evaluation",
            "train_claims":len(train_claims), "dev_claims":len(dev_claims),
            "train_cited_doc_pairs":len(train), "dev_cited_doc_pairs":len(dev),
            "dev_positive_pairs":sum(gold), "dev_negative_pairs":len(gold)-sum(gold),
            "dev_rationale_labels":dict(labels),
            "task":"cited-candidate evidence-document flag, not open retrieval",
            "baselines":scores,
            "gold_rationale_sentence_locating":{
                "evaluated":total, "direct_quote_found":positive,
                "case_whitespace_stress_found":changed,
                "unrelated_document_false_hits":negative,
                "not_scientific_entailment_accuracy":True},
            "support_contradict_semantic_task":{
                "existing_mcp_abstention_rate":1.0,
                "accuracy":None, "gold_label_predictions":0,
                "official_leaderboard_comparable":False},
            "caveats":[
                "Gold labels independent of this project.",
                "No DEV tuning; lexical cutoff selected on TRAIN.",
                "Cited candidate pool is easier than open retrieval.",
                "Comparator baselines are not competitor products.",
                "No public official test gold; no test accuracy claim.",
                "No RoB2/ROBINS-I/GRADE expert label accuracy measured.",
                "Literal text matching cannot decide SUPPORT vs CONTRADICT."
            ]}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--data", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    result = evaluate(a.data)
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(result, indent=2, sort_keys=True)+"\n")
    print(json.dumps({"status": result["status"], "dev_pairs":result["dev_cited_doc_pairs"],
                      "baselines":{k:v["dev"] for k,v in result["baselines"].items()},
                      "rationale":result["gold_rationale_sentence_locating"]}, indent=2))


if __name__ == "__main__":
    main()
