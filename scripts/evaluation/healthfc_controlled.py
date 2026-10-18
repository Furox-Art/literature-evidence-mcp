"""Conservative, opt-in syntax-only HealthFC question normalization.

No labels/evidence/author texts are changed, saved, or shipped. This parser
abstains on ambiguous punctuation, compound questions, WH questions and
unknown predicate boundaries. Accepted rows are NOT human-validated.
"""
from __future__ import annotations

import csv
import hashlib
import re
from collections import Counter
from pathlib import Path

REVISION = "9f31d765e5d4a99bd9fff667e82de503bc5684f5"
SOURCE_SHA256 = "6b832bd2a73af47f7a8d9dcd3c307defa962cff3746c26b33866170a406721c8"
SOURCE_URL = f"https://raw.githubusercontent.com/jvladika/HealthFC/{REVISION}/Datensatz.csv"
GOLD = {"0": "SUPPORT", "1": "NEUTRAL", "2": "REFUTE"}
FIELDS = {"en_claim", "en_top_sentences", "label"}

# Syntactic verb anchors, fixed before running any model against HealthFC.
# This is NOT a semantic parser or an expert meaning-preservation guarantee.
VERB_ANCHORS = (
    "accelerate", "affect", "alleviate", "alter", "avoid", "boost", "bring",
    "cause", "change", "combat", "compare", "contribute", "control", "cure",
    "damage", "decrease", "delay", "detect", "develop", "differ", "ease",
    "enhance", "extend", "fight", "get", "give", "have", "heal", "help",
    "improve", "increase", "influence", "interfere", "keep", "lead",
    "lower", "make", "measure", "mitigate", "offer", "pose", "prevent",
    "protect", "provide", "raise", "recover", "reduce", "relieve",
    "replace", "restore", "reverse", "save", "shorten", "show", "slow", "stop",
    "strengthen", "suppress", "treat", "trigger", "work", "worsen",
)
PREDICATE = re.compile(r"\b(" + "|".join(VERB_ANCHORS) + r")\b", re.IGNORECASE)
AUXILIARY = re.compile(r"^(can|could|do|does|did|will|would|should)\s+", re.IGNORECASE)
TRAIL = re.compile(r"\?+$")
AMBIGUOUS = re.compile(r"[;:\[\]{}]|\b(?:who|which|whose|whom|whether)\b", re.IGNORECASE)


def normalize_question(claim: str) -> tuple[str | None, str]:
    """Return (candidate declarative, reason), never fabricate a statement."""
    if not isinstance(claim, str) or not claim.strip():
        return None, "empty"
    claim = " ".join(claim.strip().split())
    if "?" not in claim:
        return None, "already_declarative"
    if not TRAIL.search(claim) or "?" in TRAIL.sub("", claim):
        return None, "compound_or_embedded_question"
    body = TRAIL.sub("", claim)
    if body.count(".") or body.count("!") or AMBIGUOUS.search(body):
        return None, "complex_or_ambiguous_syntax"
    auxiliary = AUXILIARY.match(body)
    if auxiliary is None:
        return None, "unsupported_question_type"
    rest = body[auxiliary.end():]
    matches = list(PREDICATE.finditer(rest))
    if not matches:
        return None, "predicate_not_identified"
    # If the first possible predicate appears in a to-infinitive or
    # negated/relative clause, the simple inversion is not trustworthy.
    pred = matches[0]
    subject = rest[:pred.start()].strip()
    predicate = rest[pred.start():].strip()
    if not subject or not predicate or not 1 <= len(subject.split()) <= 15:
        return None, "subject_boundary_unreliable"
    if subject[-1] in ",-/":
        return None, "subject_boundary_unreliable"
    if re.search(r"\b(?:to|not|no|never|that|because|if|when|although)\s*$", subject, re.IGNORECASE):
        return None, "subject_boundary_unreliable"
    if re.search(r"\b(?:that|where|while|because|although)\b", subject, re.IGNORECASE):
        return None, "subject_boundary_unreliable"
    head = auxiliary.group(1).lower()
    converted = f"{subject[0].upper()}{subject[1:]} {head} {predicate}."
    return converted, "automatic_syntax_only_unreviewed"


def read_source(path: Path) -> list[dict[str, str]]:
    """Verify immutable external bytes, row count, mapped labels and fields."""
    with path.open("rb") as handle:
        digest = hashlib.file_digest(handle, "sha256").hexdigest()
    if digest != SOURCE_SHA256:
        raise ValueError("HealthFC source SHA-256 mismatch")
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if not FIELDS <= set(reader.fieldnames or []):
            raise ValueError("HealthFC columns missing")
        rows = list(reader)
    if len(rows) != 750 or any(
        row["label"] not in GOLD or not row["en_claim"].strip()
        or not row["en_top_sentences"].strip() for row in rows
    ):
        raise ValueError("HealthFC source rows/labels/evidence invalid")
    return rows


def prepare(rows: list[dict[str, str]]) -> tuple[list[dict[str, str]], dict]:
    """Keep raw text ephemeral; aggregate excludes all corpus-derived strings."""
    prepared = []
    disposition = Counter()
    original = Counter()
    selected = Counter()
    for row in rows:
        if row["label"] not in GOLD:
            raise ValueError("Unrecognized HealthFC gold")
        gold = GOLD[row["label"]]
        original[gold] += 1
        claim, status = normalize_question(row["en_claim"])
        disposition[status] += 1
        if claim is not None:
            prepared.append({
                "claim": claim, "evidence": row["en_top_sentences"],
                "label": {"SUPPORT": "Supports", "REFUTE": "Refutes",
                          "NEUTRAL": "Neutral"}[gold],
            })
            selected[gold] += 1
    return prepared, {
        "source_sha256": SOURCE_SHA256,
        "source_revision": REVISION,
        "original_rows": len(rows),
        "original_label_distribution": dict(sorted(original.items())),
        "selected_rows": len(prepared),
        "selected_label_distribution": dict(sorted(selected.items())),
        "excluded_rows": len(rows) - len(prepared),
        "disposition": dict(sorted(disposition.items())),
        "conversion_validation": "AUTOMATED_SYNTAX_ONLY_HUMAN_REVIEW_PENDING",
        "selection_warning": "Rule-based subset not a random or representative sample.",
        "gold_semantics_warning": (
            "HealthFC expert fact-check verdicts and sentence-pair NLI "
            "entailment are not identical constructs."
        ),
    }
