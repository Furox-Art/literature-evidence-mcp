"""External ROBoto2 evidence-locator benchmark. Does NOT score RoB2 judgments.

Usage: python scripts/benchmark_roboto2.py /path/to/roboto2_dataset.csv
Requires independently authored dataset; do NOT redistribute input dataset.
Only aggregate metrics are written. Does not make network requests.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from pathlib import Path

from literature_evidence_mcp.methodology import _locate

DATA_SHA256 = "636eb757884a3fcbf5a2bfca40012b016d7800099aefe4655531ae2ed91de722"


def load_records(path: Path) -> list[dict]:
    if hashlib.sha256(path.read_bytes()).hexdigest() != DATA_SHA256:
        raise ValueError("Dataset SHA-256 mismatch; pin and document a new version explicitly")
    csv.field_size_limit(100_000_000)
    records = []
    with path.open(newline="", encoding="utf-8") as file:
        for row in csv.DictReader(file):
            parsed = json.loads(row["paper_parse"])
            annotated = json.loads(row["manual_assessment"])
            if not isinstance(parsed, dict) or not annotated:
                continue
            body = ((parsed.get("pdf_parse") or {}).get("body_text") or [])
            text = "\n".join(p.get("text", "") for p in body if isinstance(p, dict))
            if not text:
                continue
            candidates = []
            for assessment in annotated:
                for item in assessment.get("result", []):
                    rationale = item.get("rationale_text_quote") or ""
                    # Comments in the dataset are often NOT quotations. Only visibly
                    # delimited quoted passages, not reviewer speculation, are measured.
                    for fragment in re.findall(r'["“]([^"”]{24,600})["”]', rationale):
                        if len(fragment.strip().split()) >= 5:
                            candidates.append(fragment.strip())
            if candidates:
                records.append({"paper_id": row["paper_id"], "body": text,
                                "fragments": candidates})
    return records


def compute_metrics(records: list[dict]) -> dict:
    direct, shuffled, examples = [], [], 0
    for i, row in enumerate(records):
        other = records[(i + 1) % len(records)] if len(records) > 1 else None
        for fragment in row["fragments"]:
            direct.append(_locate(row["body"], fragment) is not None)
            if other is not None:
                shuffled.append(_locate(other["body"], fragment) is not None)
            examples += 1
    return {
        "dataset": "ROBoto2 (externally annotated clinical trials)",
        "dataset_sha256": DATA_SHA256,
        "evaluated_papers": len(records),
        "quoted_excerpts": examples,
        "direct_match_count": sum(direct),
        "direct_match_fraction": round(sum(direct) / len(direct), 5) if direct else None,
        "cross_paper_false_match_count": sum(shuffled),
        "cross_paper_false_match_fraction":
            round(sum(shuffled) / len(shuffled), 5) if shuffled else None,
        "metric": "verbatim excerpt retrieval against parsed PDF text",
        "independent_scientific_risk_of_bias_accuracy": "NOT_EVALUATED",
        "limitations": (
            "Quoted expert rationales can be incomplete, modified or mixed with comments; "
            "PDF parses are noisy. Positive textual retrieval is not an accurate risk-of-bias "
            "judgment. Cross-document swap controls are constructed, not gold negatives."
        ),
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("csv_path", type=Path)
    ap.add_argument("--output", type=Path, default=None)
    args = ap.parse_args()
    result = compute_metrics(load_records(args.csv_path))
    encoded = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    print(encoded)


if __name__ == "__main__":
    main()
