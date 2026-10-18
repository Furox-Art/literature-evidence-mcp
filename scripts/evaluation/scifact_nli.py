"""Zero-shot, independent SciFact rationale-level NLI audit (no DEV tuning).

Gold rationale sentences are GIVEN by SciFact, not retrieved by the MCP.
Support/refute labels exclude unknown or unlabeled papers. Incomplete evidence
is an abstention, not an independently labeled NEI gold class.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
from collections import Counter, defaultdict
from pathlib import Path

from literature_evidence_mcp.evidence_nli import (
    MODEL_ID,
    MODEL_REVISION,
    decide,
    scores_for_pairs,
)
from scripts.evaluation.scifact_open_retrieval import HASHES

THRESHOLD = .70
MARGIN = .15


def example_pairs(folder: Path, split: str) -> list[dict]:
    docs = {i["doc_id"]:i for i in map(json.loads,(folder/"corpus.jsonl").open())}
    output = []
    for line in (folder/f"claims_{split}.jsonl").read_text().splitlines():
        entry = json.loads(line)
        for key, annotation_rows in entry["evidence"].items():
            paper = docs[int(key)]
            for i, annotation in enumerate(annotation_rows):
                verdict = annotation["label"]
                if verdict not in ("SUPPORT", "CONTRADICT"):
                    raise ValueError("Unknown SciFact evidence gold")
                positions=annotation["sentences"]
                if any(type(n) is not int or not 0 <= n < len(paper["abstract"]) for n in positions):
                    raise ValueError("Gold rationale sentence missing")
                premise=" ".join(paper["abstract"][k] for k in positions)
                output.append({"claim_id":entry["id"],"document_id":int(key),
                               "annotation_number":i,"premise":premise,
                               "hypothesis":entry["claim"],"gold":verdict})
    return output


def metrics(rows: list[dict], prediction: list[str]) -> dict:
    gold=[r["gold"] for r in rows]
    if len(gold)!=len(prediction):
        raise ValueError("label vector mismatch")
    decided=[i for i,y in enumerate(prediction) if y!="INSUFFICIENT_MODEL_EVIDENCE"]
    correct=sum((gold[i]=="SUPPORT" and prediction[i]=="PREDICTED_SUPPORT") or
                (gold[i]=="CONTRADICT" and prediction[i]=="PREDICTED_REFUTE")
                for i in decided)
    return {
        "count":len(rows),
        "coverage":len(decided)/len(rows) if rows else None,
        "selective_accuracy_given_prediction": correct/len(decided) if decided else None,
        "unconditional_correct_over_all_gold_rationales":correct/len(rows) if rows else None,
        "predicted_support":sum(p=="PREDICTED_SUPPORT" for p in prediction),
        "predicted_refute":sum(p=="PREDICTED_REFUTE" for p in prediction),
        "abstained":len(rows)-len(decided),
        "gold_label_counts":dict(sorted(Counter(gold).items())),
        "confusion_matrix": {label:{result:sum(g==label and p==result for g,p in zip(gold,prediction))
             for result in ("PREDICTED_SUPPORT","PREDICTED_REFUTE","INSUFFICIENT_MODEL_EVIDENCE")}
             for label in ("SUPPORT","CONTRADICT")},
    }


def bootstrap(rows: list[dict], predictions: list[str]) -> dict:
    # Cluster entire rationale set within each scientific claim.
    groups=defaultdict(list)
    for i,row in enumerate(rows):
        groups[row["claim_id"]].append(i)
    ids=sorted(groups)
    rng=random.Random(20261018)
    cover,accuracy,unconditional=[],[],[]
    for _ in range(500):
        selected=[j for cid in rng.choices(ids,k=len(ids)) for j in groups[cid]]
        sample=metrics([rows[j] for j in selected],[predictions[j] for j in selected])
        cover.append(sample["coverage"])
        unconditional.append(sample["unconditional_correct_over_all_gold_rationales"])
        if sample["selective_accuracy_given_prediction"] is not None:
            accuracy.append(sample["selective_accuracy_given_prediction"])
    def interval(values):
        if not values:return None
        s=sorted(values)
        return [round(s[int(.025*len(s))],5),round(s[int(.975*len(s))],5)]
    return {"coverage":interval(cover),"selective_accuracy":interval(accuracy),
            "unconditional_correct":interval(unconditional)}


def evaluate(folder: Path, model_folder: Path) -> dict:
    for name,expected in HASHES.items():
        if hashlib.sha256((folder/name).read_bytes()).hexdigest()!=expected:
            raise ValueError("SciFact SHA mismatch")
    import os
    os.environ["LITERATURE_EVIDENCE_NLI_MODEL_DIR"]=str(model_folder)
    os.environ["LITERATURE_EVIDENCE_NLI_DEVICE"]=os.getenv("LITERATURE_EVIDENCE_NLI_DEVICE","cpu")
    train,dev=[example_pairs(folder,part) for part in ("train","dev")]
    majority=Counter(item["gold"] for item in train).most_common(1)[0][0]
    # SciFact DEV labels are read only for evaluation; model and threshold frozen.
    probs=scores_for_pairs([(r["premise"],r["hypothesis"]) for r in dev])
    predictions=[decide(p,THRESHOLD,MARGIN) for p in probs]
    scores=metrics(dev,predictions)
    majority_label="PREDICTED_SUPPORT" if majority=="SUPPORT" else "PREDICTED_REFUTE"
    baseline=metrics(dev,[majority_label]*len(dev))
    # Independent NLI also predicts NEUTRAL, but SciFact only supplies gold
    # SUPPORT / CONTRADICT labels here: abstention is not gold NEI accuracy.
    weight=model_folder/"model.safetensors"
    model_sha=hashlib.sha256(weight.read_bytes()).hexdigest()
    return {
        "status":"SCIFACT_EXTERNAL_NLI_GOLD_EVALUATED_WITH_ABSTENTION",
        "dataset":"SciFact publicly annotated DEV rationale sets",
        "source_dataset_file_sha256":HASHES,
        "gold_train_rationales":len(train),"gold_dev_rationales":len(dev),
        "gold_is_given_not_retrieved":True,
        "support_contradict_gold_only":True,
        "no_independent_gold_for_insufficient_class":True,
        "model":MODEL_ID,"model_revision":MODEL_REVISION,
        "model_safetensors_sha256":model_sha,
        "model_trained_on_scifact":False,
        "selection":{"threshold":THRESHOLD,"margin":MARGIN,
                     "uses_dev_for_threshold_selection":False},
        "nli_zero_shot_gold_rationale_results":scores,
        "claim_cluster_bootstrap_95pct":bootstrap(dev,predictions),
        "train_majority_class":majority,
        "train_only_majority_baseline_results":baseline,
        "no_semantic_claims_for_empty_evidence":True,
        "not_validated_scientific_truth":True,
        "limitations":[
            "Oracle SciFact gold evidence premises were handed to the model; no evidence retrieval was evaluated.",
            "SciFact train/dev rationale annotations are SUPPORT/CONTRADICT only: the NEI class is unassessed.",
            "NLIs trained on SNLI/MNLI, not scientific-domain entailment, may be overconfident.",
            "Model softmax is not calibrated scientific truth probability.",
            "No source authenticity, full-paper context, risk of bias or study quality verification.",
            "The dev partition was used only to report results, not to fit thresholds or model parameters.",
            "Any result needs human scientific adjudication before use.",
        ],
    }


def main() -> None:
    p=argparse.ArgumentParser()
    p.add_argument("--data",type=Path,required=True)
    p.add_argument("--model-dir",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    a=p.parse_args()
    result=evaluate(a.data,a.model_dir)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print("RATIONALes",result["gold_dev_rationales"])
    print("NLI",json.dumps(result["nli_zero_shot_gold_rationale_results"],sort_keys=True))
    print("MAJORITY",json.dumps(result["train_only_majority_baseline_results"],sort_keys=True))


if __name__=="__main__":
    main()
