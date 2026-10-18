"""Standalone sealed-input launcher for independent two-track diagnostics.

Usage:
  python -m scripts.evaluation.dual_track_head_to_head \
    --manifest manifest.json --gold gold.json --outputs systems.json \
    --report /tmp/dual-track-aggregate.json

Both input files must match SHA-256 hashes pre-registered in the manifest.
No network calls, raw cases, model weights or per-case outputs are published.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from literature_evidence_mcp.dual_track_audit import audit_dual_track


def _checked(path: Path, expected: str) -> object:
    if not isinstance(expected, str) or len(expected) != 64 or any(
        c not in "0123456789abcdef" for c in expected
    ):
        raise ValueError("Expected SHA-256 must be 64 lowercase hex characters")
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    if digest != expected:
        raise ValueError("Frozen input SHA-256 mismatch")
    return json.loads(path.read_text(encoding="utf-8"))


def evaluate_files(manifest_path: Path, gold_path: Path, outputs_path: Path) -> dict:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected = ("gold_sha256", "outputs_sha256", "dataset_reference", "evaluation_reference")
    if not isinstance(manifest, dict) or any(
        not isinstance(manifest.get(field), str) or not manifest[field].strip()
        for field in expected
    ):
        raise ValueError("Incomplete frozen evaluation manifest")
    if any(len(manifest[field]) > 300 for field in ("dataset_reference", "evaluation_reference")):
        raise ValueError("Manifest reference too long")
    gold = _checked(gold_path, manifest["gold_sha256"])
    outputs = _checked(outputs_path, manifest["outputs_sha256"])
    result = audit_dual_track(gold, outputs)
    result["frozen_inputs"] = {
        "gold_sha256": manifest["gold_sha256"],
        "outputs_sha256": manifest["outputs_sha256"],
        "dataset_reference": manifest["dataset_reference"],
        "evaluation_reference": manifest["evaluation_reference"],
        "integrity_verified": True,
        "independent_authority_authenticated": False,
    }
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--gold", type=Path, required=True)
    parser.add_argument("--outputs", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    result = evaluate_files(args.manifest, args.gold, args.outputs)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("DESCRIPTIVE_TWO_TRACK_COMPARISON_COMPLETE; no scientific winner")


if __name__ == "__main__":
    main()
