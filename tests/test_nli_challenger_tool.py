"""Opt-in model selection must be explicit, offline and hash-authenticated."""
from __future__ import annotations

import hashlib
from contextlib import nullcontext
from types import SimpleNamespace

import pytest

from literature_evidence_mcp import nli_challenger as challenger
from literature_evidence_mcp import server

FIRST = "fever_anli_deberta_base"
SECOND = "general_deberta_base"


@pytest.mark.parametrize("candidate", [FIRST, SECOND])
def test_no_implicit_candidate_install_or_scientific_certification(monkeypatch, candidate):
    monkeypatch.delenv(challenger.CANDIDATES[candidate]["environment"], raising=False)
    x = server.nli_assess_challenger_evidence(
        "Regular exercise improves physical health.",
        "Aerobic exercise is associated with improved cardiovascular markers.",
        "user:1", candidate,
    )
    assert x["status"] == "EXPERIMENTAL_MODEL_NOT_CONFIGURED"
    assert x["verdict"] == "INSUFFICIENT_MODEL_EVIDENCE"
    assert x["scores"] is None
    assert x["scientific_claim_verified"] is False
    assert x["production_model_modified"] is False
    assert x["required_environment_variable"] == challenger.CANDIDATES[candidate]["environment"]


@pytest.mark.parametrize("claim,evidence,source,candidate", [
    ("valid", "evidence", "source", "unlisted-model"),
    ("x", "evidence", "source", FIRST),
    ("x"*1201, "evidence", "source", FIRST),
    (None, "evidence", "source", FIRST),
    ("valid", "e", "source", FIRST),
    ("valid", "x"*2401, "source", FIRST),
    ("valid", None, "source", FIRST),
    ("valid", "evidence", "", FIRST),
    ("valid", "evidence", 123, FIRST),
    ("valid", "evidence", "x"*257, FIRST),
])
def test_malformed_input_fails_closed(claim, evidence, source, candidate):
    with pytest.raises(ValueError):
        challenger.assess_candidate(claim, evidence, source, candidate)


@pytest.mark.parametrize("scores,verdict", [
    ({"contradiction": .01, "entailment": .98, "neutral": .01}, "PREDICTED_SUPPORT"),
    ({"contradiction": .98, "entailment": .01, "neutral": .01}, "PREDICTED_REFUTE"),
    ({"contradiction": .1, "entailment": .1, "neutral": .8},
     "INSUFFICIENT_MODEL_EVIDENCE"),
])
def test_configured_challenger_remains_uncalibrated(monkeypatch, scores, verdict):
    monkeypatch.setenv(challenger.CANDIDATES[FIRST]["environment"], "/tmp/known-model")
    monkeypatch.setattr(challenger, "candidate_scores", lambda *a: scores)
    result = server.nli_assess_challenger_evidence(
        "Hypothesis about neurons", "Observed neuron signal", "caller:id", FIRST,
    )
    assert result["status"] == "EXPERIMENTAL_MODEL_PREDICTION_NOT_PROOF"
    assert result["verdict"] == verdict
    assert result["scores"] == scores
    assert result["scores_calibrated"] is False
    assert result["source_authenticity_verified"] is False
    assert result["experimental"] is True
    assert len(result["input_evidence_sha256"]) == 64


def test_configured_but_model_files_or_dependencies_absent(monkeypatch):
    monkeypatch.setenv(challenger.CANDIDATES[FIRST]["environment"], "/tmp/unknown")
    def missing(*args):
        raise FileNotFoundError("missing")
    monkeypatch.setattr(challenger, "candidate_scores", missing)
    assert challenger.assess_candidate("claim", "evidence", "source", FIRST)[
        "status"] == "PINNED_MODEL_FILES_MISSING"
    for dep in ("torch", "transformers", "sentencepiece"):
        def absent(*args, name=dep):
            raise ModuleNotFoundError("optional dep", name=name)
        monkeypatch.setattr(challenger, "candidate_scores", absent)
        assert challenger.assess_candidate("claim", "evidence", "source", FIRST)[
            "status"] == "OPTIONAL_NLI_DEPENDENCY_MISSING"
    def nested(*args):
        raise ModuleNotFoundError("unexpected", name="unrelated-module")
    monkeypatch.setattr(challenger, "candidate_scores", nested)
    with pytest.raises(ModuleNotFoundError):
        challenger.assess_candidate("claim", "evidence", "source", FIRST)


def test_files_all_require_exact_sha(monkeypatch, tmp_path):
    payload = b"frozen model artifact"
    manifest = {"model.safetensors": hashlib.sha256(payload).hexdigest()}
    monkeypatch.setitem(challenger.CANDIDATES[FIRST], "files", manifest)
    with pytest.raises(FileNotFoundError):
        challenger.verify_candidate_files(FIRST, tmp_path)
    (tmp_path / "model.safetensors").write_bytes(b"tampered")
    with pytest.raises(ValueError, match="checksum"):
        challenger.verify_candidate_files(FIRST, tmp_path)
    (tmp_path / "model.safetensors").write_bytes(payload)
    challenger.verify_candidate_files(FIRST, tmp_path)


def test_model_loads_offline_only_and_rejects_unknown_mapping(monkeypatch, tmp_path):
    challenger._load_candidate.cache_clear()
    monkeypatch.setattr(challenger, "verify_candidate_files", lambda *args: None)

    class FakeModel:
        def __init__(self):
            self.config = SimpleNamespace(id2label={
                0: "entailment", 1: "neutral", 2: "contradiction"})
        def to(self, device):
            assert device == "cpu"
            return self
        def eval(self):
            return self

    fake_model = FakeModel()
    tokenizer = "TEST_TOKENIZER"
    fake_transformers = SimpleNamespace(
        AutoTokenizer=SimpleNamespace(from_pretrained=lambda *args, **kw: tokenizer),
        AutoModelForSequenceClassification=SimpleNamespace(
            from_pretrained=lambda *args, **kw: fake_model),
    )
    fake_torch = SimpleNamespace(cuda=SimpleNamespace(is_available=lambda: False))
    monkeypatch.setattr(challenger.importlib, "import_module",
                        lambda name: fake_torch if name == "torch" else fake_transformers)
    assert challenger._load_candidate(FIRST, str(tmp_path), "cpu")[0] == tokenizer
    challenger._load_candidate.cache_clear()
    with pytest.raises(ValueError, match="compute device"):
        challenger._load_candidate(FIRST, str(tmp_path), "mps")
    challenger._load_candidate.cache_clear()
    with pytest.raises(ValueError, match="compute device"):
        challenger._load_candidate(FIRST, str(tmp_path), "cuda")
    challenger._load_candidate.cache_clear()
    fake_model.config.id2label = {0:"LABEL_0",1:"LABEL_1",2:"LABEL_2"}
    with pytest.raises(ValueError, match="label map"):
        challenger._load_candidate(FIRST, str(tmp_path), "cpu")
    challenger._load_candidate.cache_clear()


def test_score_uses_actual_label_map_not_fixed_order(monkeypatch):
    class Tensor:
        def __init__(self, rows):
            self.rows = rows
        def to(self, device):
            assert device == "cpu"
            return self
        def __getitem__(self, index):
            return self
        def cpu(self):
            return self
        def tolist(self):
            return self.rows[0]

    class Tokenizer:
        def __call__(self, evidence, claim, **kwargs):
            assert "evidence" in evidence
            assert "claim" in claim
            assert kwargs["max_length"] == 512
            return {"input_ids": Tensor([[1]])}

    class Model:
        def __call__(self, **kwargs):
            return SimpleNamespace(logits=Tensor([[.91,.05,.04]]))

    fake_torch = SimpleNamespace(inference_mode=lambda: nullcontext(),
                                 softmax=lambda logits, dim: logits)
    monkeypatch.setattr(challenger, "_load_candidate", lambda *args:
                        (Tokenizer(), Model(), fake_torch, "cpu",
                         {0:"entailment",1:"neutral",2:"contradiction"}))
    out = challenger.candidate_scores(FIRST, "my evidence", "my claim", "/tmp/model")
    assert out == {"entailment": .91, "neutral": .05, "contradiction": .04}
