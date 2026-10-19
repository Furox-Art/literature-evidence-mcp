"""Byte-only integrity audit for prospective *candidate* evaluation data.

Never parses gold test labels or prints any original text, query, or evidence.
This is NOT blind evaluation, contamination clearance or an approved protocol.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from pathlib import Path

CANDIDATES = {
    "retrieval": {
        "name": "BEIR NFCorpus",
        "upstream": "beir-cellar/beir, nfcorpus.zip",
        "url": "https://public.ukp.informatik.tu-darmstadt.de/thakur/BEIR/datasets/nfcorpus.zip",
        "sha256": "efe5be03f8c5b86a5870102d0599d227c8c6e2484328e68c6522560385671b0b",
        "md5": "a89dba18a62ef92f7d323ec890a0d38d",
        "license": "CC-BY-SA-4.0 (upstream BEIR card; verify original article rights)",
        "members": (
            "nfcorpus/corpus.jsonl", "nfcorpus/queries.jsonl",
            "nfcorpus/qrels/train.tsv", "nfcorpus/qrels/dev.tsv",
            "nfcorpus/qrels/test.tsv",
        ),
        "scope": "fixed 3633-document biomedical corpus, 323 published test queries",
    },
    "classification": {
        "name": "VitaminC test",
        "upstream": "tals/vitaminc",
        "url": "https://huggingface.co/datasets/tals/vitaminc/resolve/"
               "be6febb761b0b2807687e61e0b5282e459df2fa0/test.jsonl",
        "revision": "be6febb761b0b2807687e61e0b5282e459df2fa0",
        "sha256": "7ad1808dbc30c62e0a1427a53022d0dfaff668a1fde3c4b612a2d266edd753ad",
        "size_bytes": 28717099,
        "license": "CC-BY-SA-3.0 and per-page Wikipedia copyright terms",
        "scope": "55197 public test pairs, Wikipedia-edit domain, not biomedical expert validation",
    },
}


def _digest(path: Path, method: str) -> str:
    result = hashlib.new(method)
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            result.update(chunk)
    return result.hexdigest()


def verify(retrieval_archive: Path, classification_test: Path) -> dict:
    output = {}
    for task, path in (("retrieval", retrieval_archive),
                       ("classification", classification_test)):
        pinned = CANDIDATES[task]
        if not path.is_file():
            raise FileNotFoundError("Missing frozen external test file: " + task)
        if _digest(path, "sha256") != pinned["sha256"]:
            raise ValueError("Candidate SHA-256 mismatch: " + task)
        if "md5" in pinned and _digest(path, "md5") != pinned["md5"]:
            raise ValueError("Official source MD5 mismatch: " + task)
        if "size_bytes" in pinned and path.stat().st_size != pinned["size_bytes"]:
            raise ValueError("Candidate size mismatch: " + task)
        if task == "retrieval":
            with zipfile.ZipFile(path) as archive:
                members = [entry.filename for entry in archive.infolist()
                           if not entry.is_dir()]
                if len(members) != len(set(members)):
                    raise ValueError("Archive contains duplicate filenames")
                if any(name.startswith("/") or ".." in name.split("/")
                       or "\\" in name for name in members):
                    raise ValueError("Unsafe archive member path")
                if set(pinned["members"]) != set(members):
                    raise ValueError("Official source archive member mismatch")
            structural_count = len(members)
        else:
            # Scan line delimiters only. Do not parse claims, evidence, or gold labels.
            with path.open("rb") as stream:
                structural_count = sum(bool(line.strip()) for line in stream)
            if structural_count != 55197:
                raise ValueError("Candidate test line count mismatch")
        output[task] = {
            "name": pinned["name"], "url": pinned["url"],
            "sha256": pinned["sha256"],
            "license_notice": pinned["license"],
            "structural_count": structural_count,
            "integrity_status": "BYTE_PIN_VERIFIED",
            "gold_labels_inspected": False,
            "scientific_independence_confirmed": False,
            "blinding_confirmed": False,
            "data_redistributed": False,
            "scope_warning": pinned["scope"],
        }
    return {
        "status": "SOURCE_INTEGRITY_VERIFIED_SCIENTIFIC_EVALUATION_NOT_RUN",
        "datasets": output,
        "scientific_superiority_demonstrated": False,
        "outstanding": [
            "Select primary metrics and gold mapping before inspecting test labels",
            "Compare actual versions of named competitors on matched cases",
            "Check data license and public pretraining leakage risk",
            "NFCorpus evaluates fixed-corpus ranking, not live provider search",
            "VitaminC tests Wikipedia claim-evidence pairs, not clinical fact checking",
            "Independent blinded expert assessment requires new prospective cases",
        ],
    }


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--retrieval-zip", type=Path, required=True)
    p.add_argument("--classification-jsonl", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    report = verify(args.retrieval_zip, args.classification_jsonl)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, sort_keys=True, indent=2) + "\n",
                           encoding="utf-8")
    print("CANDIDATES_VERIFIED_NO_GOLD_READ_NO_SCIENTIFIC_TEST")


if __name__ == "__main__":
    main()
