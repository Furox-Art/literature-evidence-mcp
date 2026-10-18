"""Optional, OFFLINE-only, provenance-bound NLI estimates, not scientific proof.

Premise: user-supplied evidence text. Hypothesis: user-supplied claim.
Outputs are *model predictions* and abstention, not facts or expert ratings.
"""
from __future__ import annotations

import hashlib
import importlib
import math
import os
from functools import lru_cache
from pathlib import Path

MODEL_ID = "cross-encoder/nli-deberta-v3-small"
MODEL_REVISION = "fa2804872c3b4bd748f38c0185cc85775361e735"
WEIGHTS_SHA256 = "ebc79588dd73ccfb6a3f6078519cfbf512c5305384c5ea1845bc71cd32216e86"
LABELS = ("contradiction", "entailment", "neutral")


def decide(scores: dict[str, float], threshold: float = 0.70,
           margin: float = 0.15) -> str:
    """Conservative three-way verdict with explicit insufficient evidence."""
    if set(scores) != set(LABELS) or any(
        type(score) not in (float, int) or not math.isfinite(score) or
        score < 0 or score > 1 for score in scores.values()
    ):
        raise ValueError("finite three-label probabilities required")
    if abs(sum(scores.values()) - 1) > 0.005:
        raise ValueError("NLI probabilities must sum to one")
    if type(threshold) not in (int, float) or not 0.5 <= threshold <= 1.0:
        raise ValueError("threshold must be 0.5-1")
    if type(margin) not in (int, float) or not 0 <= margin <= 1.0:
        raise ValueError("margin must be 0-1")
    ranked = sorted(LABELS, key=lambda label: scores[label], reverse=True)
    winner = ranked[0]
    if (winner == "neutral" or scores[winner] < threshold or
            scores[winner] - scores[ranked[1]] < margin):
        return "INSUFFICIENT_MODEL_EVIDENCE"
    return "PREDICTED_SUPPORT" if winner == "entailment" else "PREDICTED_REFUTE"


@lru_cache(maxsize=1)
def _load_model():
    """Load only previously downloaded safetensors; never download implicitly."""
    location = os.getenv("LITERATURE_EVIDENCE_NLI_MODEL_DIR", "")
    if not location:
        raise FileNotFoundError("NLI model directory not configured")
    path = Path(location)
    if not path.is_dir() or not (path / "model.safetensors").is_file():
        raise FileNotFoundError("Pinned local safetensors not found")
    # Verify actual model bytes, not just an untrusted directory name.
    with (path / "model.safetensors").open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    if digest != WEIGHTS_SHA256:
        raise ValueError("Model weights SHA-256 differs from pinned revision")
    tr = importlib.import_module("transformers")
    torch = importlib.import_module("torch")
    tokenizer = tr.AutoTokenizer.from_pretrained(
        str(path), local_files_only=True, trust_remote_code=False)
    model = tr.AutoModelForSequenceClassification.from_pretrained(
        str(path), local_files_only=True, trust_remote_code=False,
        use_safetensors=True)
    label_map = {int(k): str(v).lower() for k, v in model.config.id2label.items()}
    if label_map != dict(enumerate(LABELS)):
        raise ValueError("Pinned NLI label mapping mismatch")
    device = os.getenv("LITERATURE_EVIDENCE_NLI_DEVICE", "cpu")
    if device not in {"cpu", "cuda"}:
        raise ValueError("NLI device must be cpu or cuda")
    if device == "cuda" and not torch.cuda.is_available():
        raise ValueError("CUDA requested but not available")
    model.to(device)
    model.eval()
    return tokenizer, model, torch, device


def scores_for_pairs(pairs: list[tuple[str, str]]) -> list[dict[str, float]]:
    """Runs fixed local model on (evidence premise, scientific claim hypothesis)."""
    tokenizer, model, torch, device = _load_model()
    results: list[dict[str, float]] = []
    for start in range(0, len(pairs), 16):
        chunk = pairs[start:start + 16]
        inputs = tokenizer(
            [p[0] for p in chunk], [p[1] for p in chunk],
            truncation=True, padding=True, max_length=512,
            return_tensors="pt",
        )
        inputs = {key: value.to(device) for key, value in inputs.items()}
        with torch.inference_mode():
            logits = model(**inputs).logits
            probabilities = torch.softmax(logits, dim=-1).cpu().tolist()
        for row in probabilities:
            results.append(dict(zip(LABELS, [float(x) for x in row])))
    return results


def assess_evidence_nli(
    claim: str, evidence: str, source_id: str,
    threshold: float = 0.70, margin: float = 0.15,
) -> dict:
    """Return model prediction or explicit inability to assess, never 'verified'."""
    if not isinstance(claim, str) or not 2 <= len(claim.strip()) <= 1200:
        raise ValueError("claim must be 2-1200 characters")
    if not isinstance(evidence, str) or not 2 <= len(evidence.strip()) <= 2400:
        raise ValueError("evidence must be 2-2400 characters")
    if not isinstance(source_id, str) or not 1 <= len(source_id.strip()) <= 256:
        raise ValueError("nonempty source_id of at most 256 characters required")
    # Reject invalid thresholds before attempting any model installation.
    decide(dict(zip(LABELS, (0.0, 0.0, 1.0))), threshold, margin)
    shared = {
        "model_id": MODEL_ID, "model_revision": MODEL_REVISION,
        "weights_sha256_expected": WEIGHTS_SHA256,
        "source_id": source_id,
        "supplied_text_sha256": hashlib.sha256(evidence.encode()).hexdigest(),
        "scientific_claim_verified": False,
        "publisher_source_authenticated": False,
        "calibrated_probability": False,
        "truncation_limit_tokens": 512,
    }
    if not os.getenv("LITERATURE_EVIDENCE_NLI_MODEL_DIR"):
        return {**shared, "status": "LOCAL_MODEL_NOT_CONFIGURED",
                "verdict": "INSUFFICIENT_MODEL_EVIDENCE", "scores": None}
    try:
        probabilities = scores_for_pairs([(evidence, claim)])[0]
    except ModuleNotFoundError as exc:
        if exc.name not in {"torch", "transformers", "sentencepiece"}:
            raise
        return {**shared, "status": "OPTIONAL_NLI_DEPENDENCY_MISSING",
                "verdict": "INSUFFICIENT_MODEL_EVIDENCE", "scores": None}
    except FileNotFoundError:
        return {**shared, "status": "LOCAL_MODEL_FILES_MISSING",
                "verdict": "INSUFFICIENT_MODEL_EVIDENCE", "scores": None}
    label = decide(probabilities, threshold, margin)
    return {
        **shared, "status": "MODEL_PREDICTION_NOT_SCIENTIFIC_PROOF",
        "verdict": label, "scores": probabilities, "threshold": threshold,
        "minimum_margin": margin,
        "notice": "SNLI/MNLI-trained NLI model; scientific-domain precision, "
                  "contradiction and abstention are not guaranteed. Human review required.",
    }
