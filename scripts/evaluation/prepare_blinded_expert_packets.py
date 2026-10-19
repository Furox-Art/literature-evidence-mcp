"""Prepare label-blinded general-science evidence packets for future review.

Does not recruit expert reviewers or claim independence, prospective blinding,
accuracy, consensus, study eligibility, or scientific gold annotation.

Use only permissioned source documents. Outputs remain outside normal Git.
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
from pathlib import Path

FIELDS = frozenset({
    "candidate_id", "claim", "evidence", "source_doi", "source_locator",
    "publication_type", "collection_date", "source_id", "source_url",
    "discipline",
})
REQUIRED = frozenset({"candidate_id", "claim", "evidence", "source_locator"})
SOURCE_IDENTIFIERS = frozenset({"source_doi", "source_id", "source_url"})
FORBIDDEN = frozenset({
    "label", "gold", "prediction", "predicted_label", "model", "model_output",
    "reference_answer", "reviewer_answer", "consensus", "quality_score",
})


def validate_cases(cases: object) -> list[dict]:
    if not isinstance(cases, list) or not 1 <= len(cases) <= 1000:
        raise ValueError("Supply 1-1000 independent candidate records")
    used = set()
    result = []
    for row in cases:
        if not isinstance(row, dict):
            raise TypeError("Each candidate must be an object")
        keys = set(row)
        if keys & FORBIDDEN or keys - FIELDS or not REQUIRED <= keys:
            raise ValueError("Unapproved input, missing source, or possible answer leakage")
        if not keys & SOURCE_IDENTIFIERS:
            raise ValueError("At least one source identifier (DOI, ID, URL) required")
        clean = {}
        for field in sorted(keys):
            value = row[field]
            if not isinstance(value, str) or not value.strip() or len(value) > 24000:
                raise ValueError("Candidate fields require nonempty bounded text")
            if field in {"candidate_id", "source_doi", "source_id", "collection_date"} and len(value) > 260:
                raise ValueError("Overlong identifier")
            clean[field] = value.strip()
        candidate_id = clean["candidate_id"]
        if candidate_id in used:
            raise ValueError("Duplicate candidate identity")
        used.add(candidate_id)
        result.append(clean)
    return result


def create_packet(cases: list[dict], secret: bytes) -> tuple[bytes, bytes, dict]:
    if not isinstance(secret, bytes) or len(secret) < 32:
        raise ValueError("Independent cryptographic random secret required")
    clean = validate_cases(cases)
    blinded = []
    mapping = []
    for row in clean:
        ident = hmac.new(secret, row["candidate_id"].encode(), hashlib.sha256).hexdigest()[:32]
        if any(item["blind_id"] == ident for item in blinded):
            raise ValueError("Blinded identifier collision")
        # Input order must not encode cohort order to reviewers.
        blinded.append({"blind_id": ident, **{k: v for k, v in row.items()
                                              if k != "candidate_id"}})
        mapping.append({"blind_id": ident, "candidate_id": row["candidate_id"]})
    blinded.sort(key=lambda x: x["blind_id"])
    mapping.sort(key=lambda x: x["blind_id"])
    packet = "".join(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n"
                     for item in blinded).encode("utf-8")
    private = (json.dumps({"mapping": mapping}, sort_keys=True, indent=2) + "\n").encode()
    metadata = {
        "status": "REVIEW_PACKET_PREPARED_NO_EXPERT_ASSESSMENT",
        "item_count": len(clean),
        "packet_sha256": hashlib.sha256(packet).hexdigest(),
        "private_mapping_sha256": hashlib.sha256(private).hexdigest(),
        "classification_or_relevance_gold_generated": False,
        "independent_expert_annotation_verified": False,
        "blindness_verified": False,
        "inter_rater_reliability_estimated": False,
        "candidate_provenance_externally_authenticated": False,
        "notes": [
            "Packets do not contain source candidate IDs or any model decisions.",
            "Source metadata can reveal provenance or study identity; full blinding not guaranteed.",
            "Any science discipline is permitted; expert subject competence must be verified separately.",
            "Private mapping and reviewer packet require separately controlled destinations.",
            "The user must approve eligibility, sampling, adjudication, and primary outcomes.",
            "External qualified experts must actually label records before blind validation.",
        ],
    }
    return packet, private, metadata


def _write_new_private(path: Path, content: bytes) -> None:
    # Exclusive create with owner-only permissions. Never silently overwrite
    # existing reviewer responses or unblinded mappings.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(content)
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def write_packet(
    input_file: Path, review_packet: Path, private_mapping: Path, manifest: Path,
    secret: bytes,
) -> dict:
    targets = [review_packet.resolve(), private_mapping.resolve(), manifest.resolve()]
    if len(set(targets)) != 3 or review_packet.parent.resolve() == private_mapping.parent.resolve():
        raise ValueError("Unique output paths; separate blind and private directories required")
    if input_file.resolve() in targets:
        raise ValueError("Source input cannot be overwritten")
    if any(target.exists() for target in targets):
        raise FileExistsError("Output exists; never replace frozen evidence")
    cases = json.loads(input_file.read_text(encoding="utf-8"))
    packet, mapping, report = create_packet(cases, secret)
    review_packet.parent.mkdir(parents=True, exist_ok=True)
    private_mapping.parent.mkdir(parents=True, exist_ok=True)
    manifest.parent.mkdir(parents=True, exist_ok=True)
    created: list[Path] = []
    try:
        for target, payload in (
            (review_packet, packet),
            (private_mapping, mapping),
            (manifest, (json.dumps(report, indent=2, sort_keys=True) + "\n").encode()),
        ):
            _write_new_private(target, payload)
            created.append(target)
    except BaseException:
        # A half-published review packet has no valid freeze manifest and must
        # not be left behind after a later write failure.
        for target in reversed(created):
            target.unlink(missing_ok=True)
        raise
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--review-packet", type=Path, required=True)
    parser.add_argument("--private-map", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--secret-env", default="REVIEW_PACKET_SECRET_HEX")
    args = parser.parse_args()
    env = os.environ.get(args.secret_env, "")
    try:
        secret = bytes.fromhex(env)
    except ValueError as exc:
        raise ValueError("Secret must be valid 32+-byte hex provided through environment") from exc
    result = write_packet(args.input, args.review_packet, args.private_map,
                          args.manifest, secret)
    print(json.dumps({"status": result["status"], "item_count": result["item_count"],
                      "packet_sha256": result["packet_sha256"]}))


if __name__ == "__main__":
    main()
