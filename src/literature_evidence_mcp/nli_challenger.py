"""Explicitly opt-in, pinned NLI candidate inference (never production replacement)."""
from __future__ import annotations

import hashlib
import importlib
import os
from functools import lru_cache
from pathlib import Path

from literature_evidence_mcp.evidence_nli import LABELS, decide

CANDIDATES = {
    "fever_anli_deberta_base": {
        "id": "MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli",
        "revision": "6f5cf0a2b59cabb106aca4c287eed12e357e90eb",
        "license": "mit",
        "environment": "LITERATURE_EVIDENCE_NLI_FEVER_MODEL_DIR",
        "files": {
            "model.safetensors": "06d6fd89edd4f97816831626daafbdb0b029cf63bae8edc0bccab1d64e2e7707",
            "config.json": "a6c616d6dabeacf90fd0e776c741d3f0f30a05533ccf0bd3b5b62e94cfaa8d57",
            "tokenizer.json": "05402ffae6dd382a8491b1d29bfc139bec5d332662e86a026f433ce54c25c202",
            "tokenizer_config.json": "557b3d33d3f41b81ad769244e506549e98a1857d41dd58160aacd4d98d710b5a",
            "spm.model": "c679fbf93643d19aab7ee10c0b99e460bdbc02fedf34b92b05af343b4af586fd",
            "special_tokens_map.json": "9463f61e1b109a8eb4688b829260d7c6b1e6dff04c98ff7269bb89e2b92369b9",
            "added_tokens.json": "dc046d04c9b0ada7ae6f1dc89c465801799acdf0c9a6aab8c15a1b2d5ca4e91f",
        },
    },
    "general_deberta_base": {
        "id": "cross-encoder/nli-deberta-v3-base",
        "revision": "6c749ce3425cd33b46d187e45b92bbf96ee12ec7",
        "license": "apache-2.0",
        "environment": "LITERATURE_EVIDENCE_NLI_GENERAL_MODEL_DIR",
        "files": {
            "model.safetensors": "d8148c6d49e0a7925134294c56326c71fe0ab1dc390e37355e00c7efbb488afa",
            "config.json": "897e756eb59d3183adb505952e7910e7cbc7750a43f3b3747a96b688d2b02a47",
            "tokenizer.json": "5124ef2ead1a10a717703bc436de7f353da76d6340e4587719b42b1693707964",
            "tokenizer_config.json": "f3eecd07c370ef0bf7dd3780d3cd68cf9c8b00c267e21a208ddcd8f82bfec1a6",
            "spm.model": "c679fbf93643d19aab7ee10c0b99e460bdbc02fedf34b92b05af343b4af586fd",
            "special_tokens_map.json": "ed7c099c988dbb414b18a6980d20cb57b91b7cd119f6f6941eb364b0e892e712",
            "added_tokens.json": "a4b6bfe668f2b3cf6f0cd535e98a0663d2d0d4a4a15f13075ad3597d33985a23",
        },
    },
}


def verify_candidate_files(candidate: str, location: Path) -> None:
    """Fail closed on any missing or modified pinned checkpoint component."""
    expected = CANDIDATES[candidate]["files"]
    for filename, checksum in expected.items():
        path = location / filename
        if not path.is_file():
            raise FileNotFoundError(f"Pinned NLI model component missing: {filename}")
        with path.open("rb") as stream:
            if hashlib.file_digest(stream, "sha256").hexdigest() != checksum:
                raise ValueError(f"Pinned NLI model component checksum mismatch: {filename}")


@lru_cache(maxsize=2)
def _load_candidate(candidate: str, location: str, device: str):
    """Only pinned local model files, never remote code or network access."""
    verify_candidate_files(candidate, Path(location))
    torch = importlib.import_module("torch")
    transformers = importlib.import_module("transformers")
    if device not in {"cpu", "cuda"} or (device == "cuda" and not torch.cuda.is_available()):
        raise ValueError("Requested NLI candidate compute device unavailable")
    tokenizer = transformers.AutoTokenizer.from_pretrained(
        location, local_files_only=True, trust_remote_code=False,
    )
    model = transformers.AutoModelForSequenceClassification.from_pretrained(
        location, local_files_only=True, trust_remote_code=False, use_safetensors=True,
    )
    found = {int(k): str(v).lower() for k, v in model.config.id2label.items()}
    if set(found) != {0, 1, 2} or set(found.values()) != set(LABELS):
        raise ValueError("NLI candidate classification label map unexpected")
    model.to(device).eval()
    return tokenizer, model, torch, device, found


def candidate_scores(candidate: str, evidence: str, claim: str, location: str
                     ) -> dict[str, float]:
    device = os.getenv("LITERATURE_EVIDENCE_NLI_DEVICE", "cpu")
    tokenizer, model, torch, used_device, classes = _load_candidate(
        candidate, location, device,
    )
    encoded = tokenizer(evidence, claim, truncation=True, padding=True,
                        max_length=512, return_tensors="pt")
    encoded = {key: value.to(used_device) for key, value in encoded.items()}
    with torch.inference_mode():
        logits = model(**encoded).logits
        probs = torch.softmax(logits, dim=-1)[0].cpu().tolist()
    return {classes[i]: float(prob) for i, prob in enumerate(probs)}


def assess_candidate(claim: str, evidence: str, source_id: str, candidate: str) -> dict:
    """Model scores are uncalibrated; separate from core fact/quote verification."""
    if candidate not in CANDIDATES:
        raise ValueError("Unknown NLI challenger; explicit allowlisted model key required")
    if not isinstance(claim, str) or not 2 <= len(claim.strip()) <= 1200:
        raise ValueError("claim must be a 2-1200 character string")
    if not isinstance(evidence, str) or not 2 <= len(evidence.strip()) <= 2400:
        raise ValueError("evidence must be a 2-2400 character string")
    if not isinstance(source_id, str) or not 1 <= len(source_id.strip()) <= 256:
        raise ValueError("source_id must be a nonempty string, maximum 256 characters")
    specification = CANDIDATES[candidate]
    base = {
        "model_key": candidate, "model_id": specification["id"],
        "model_revision": specification["revision"],
        "weights_sha256": specification["files"]["model.safetensors"],
        "input_evidence_sha256": hashlib.sha256(evidence.encode()).hexdigest(),
        "source_id": source_id, "scores_calibrated": False,
        "scientific_claim_verified": False, "source_authenticity_verified": False,
        "production_model_modified": False, "experimental": True,
    }
    location = os.getenv(specification["environment"])
    if not location:
        return {**base, "status": "EXPERIMENTAL_MODEL_NOT_CONFIGURED",
                "verdict": "INSUFFICIENT_MODEL_EVIDENCE", "scores": None,
                "required_environment_variable": specification["environment"]}
    try:
        scores = candidate_scores(candidate, evidence, claim, location)
    except FileNotFoundError:
        return {**base, "status": "PINNED_MODEL_FILES_MISSING",
                "verdict": "INSUFFICIENT_MODEL_EVIDENCE", "scores": None}
    except ModuleNotFoundError as exc:
        if exc.name not in {"torch", "transformers", "sentencepiece"}:
            raise
        return {**base, "status": "OPTIONAL_NLI_DEPENDENCY_MISSING",
                "verdict": "INSUFFICIENT_MODEL_EVIDENCE", "scores": None}
    return {**base, "status": "EXPERIMENTAL_MODEL_PREDICTION_NOT_PROOF",
            "verdict": decide(scores, .70, .15),
            "scores": scores, "threshold": .70, "margin": .15,
            "notice": "Exploratory third-party NLI candidate. Cannot infer medical truth, "
                      "source authenticity, causal effects, or evidence sufficiency. "
                      "Previously inspected HealthVer TEST used for model comparison."}
