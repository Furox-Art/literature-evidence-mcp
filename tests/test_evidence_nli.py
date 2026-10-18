"""NLI is a machine estimate, never a scientific proof or valid gold source."""
from __future__ import annotations

from contextlib import nullcontext
from types import SimpleNamespace

import pytest

from literature_evidence_mcp import evidence_nli as nli
from literature_evidence_mcp import server


def test_decision_support_refute_neutral_low_confidence_and_margin():
    assert nli.decide({"entailment": .96, "contradiction": .02, "neutral": .02}) == "PREDICTED_SUPPORT"
    assert nli.decide({"entailment": .03, "contradiction": .96, "neutral": .01}) == "PREDICTED_REFUTE"
    assert nli.decide({"entailment": .01, "contradiction": .01, "neutral": .98}) == "INSUFFICIENT_MODEL_EVIDENCE"
    assert nli.decide({"entailment": .6, "contradiction": .22, "neutral": .18}) == "INSUFFICIENT_MODEL_EVIDENCE"
    assert nli.decide({"entailment": .51, "contradiction": .48, "neutral": .01}, .5, .20) == "INSUFFICIENT_MODEL_EVIDENCE"
    assert nli.decide({"entailment": .75, "contradiction": .20, "neutral": .05}, .7, .15) == "PREDICTED_SUPPORT"


@pytest.mark.parametrize("scores", [
    {"neutral": 1.0},
    {"neutral": .5, "entailment": .2, "contradiction": .2},
    {"neutral": float("nan"), "entailment": .5, "contradiction": .5},
    {"neutral": -.1, "entailment": .5, "contradiction": .6},
    {"neutral": 1.1, "entailment": -.1, "contradiction": 0},
    {"neutral": "1", "entailment": 0, "contradiction": 0},
])
def test_invalid_probabilities_rejected(scores):
    with pytest.raises(ValueError):
        nli.decide(scores)


@pytest.mark.parametrize("threshold,margin", [(0.4,.1),(1.1,.1),(True,.1),(.7,-.1),(.7,1.1),(.7,True)])
def test_invalid_thresholds_rejected(threshold, margin):
    with pytest.raises(ValueError):
        nli.decide({"neutral": .2, "entailment": .7, "contradiction": .1}, threshold, margin)


@pytest.mark.parametrize("claim,evidence,source", [
    (None, "evidence", "doi:1"), ("x", "evidence", "doi:1"),
    ("x"*1201, "evidence", "doi:1"), ("claim", None, "doi:1"),
    ("claim", "x", "doi:1"), ("claim", "x"*2401, "doi:1"),
    ("claim", "evidence", ""), ("claim", "evidence", 42),
    ("claim", "evidence", "x"*257),
])
def test_invalid_inputs_rejected(claim, evidence, source):
    with pytest.raises(ValueError):
        server.nli_assess_evidence(claim, evidence, source)


def test_default_is_safe_offline_abstention(monkeypatch):
    monkeypatch.delenv("LITERATURE_EVIDENCE_NLI_MODEL_DIR", raising=False)
    result = server.nli_assess_evidence("Some hypothesis", "Some evidence", "sha:abc")
    assert result["status"] == "LOCAL_MODEL_NOT_CONFIGURED"
    assert result["verdict"] == "INSUFFICIENT_MODEL_EVIDENCE"
    assert result["scientific_claim_verified"] is False
    assert result["scores"] is None
    assert len(result["supplied_text_sha256"]) == 64


def test_configured_model_prediction_and_honest_uncalibrated_output(monkeypatch):
    monkeypatch.setenv("LITERATURE_EVIDENCE_NLI_MODEL_DIR", "/tmp/nli-test")
    monkeypatch.setattr(nli, "scores_for_pairs", lambda pairs:
                        [{"contradiction": .01, "entailment": .98, "neutral": .01}])
    result = server.nli_assess_evidence("Neural hypothesis", "Neural observed", "doi:known")
    assert result["verdict"] == "PREDICTED_SUPPORT"
    assert result["status"] == "MODEL_PREDICTION_NOT_SCIENTIFIC_PROOF"
    assert result["calibrated_probability"] is False
    assert result["publisher_source_authenticated"] is False
    assert result["model_revision"] == nli.MODEL_REVISION


@pytest.mark.parametrize("name,status", [
    ("torch", "OPTIONAL_NLI_DEPENDENCY_MISSING"),
    ("transformers", "OPTIONAL_NLI_DEPENDENCY_MISSING"),
    ("sentencepiece", "OPTIONAL_NLI_DEPENDENCY_MISSING"),
])
def test_optional_missing_package_is_explicit(monkeypatch, name, status):
    monkeypatch.setenv("LITERATURE_EVIDENCE_NLI_MODEL_DIR", "/tmp/nli-test")
    def missing(pairs):
        raise ModuleNotFoundError("missing", name=name)
    monkeypatch.setattr(nli, "scores_for_pairs", missing)
    assert server.nli_assess_evidence("Hypothesis", "Evidence", "paper")["status"] == status


def test_transitive_missing_package_is_not_hidden(monkeypatch):
    monkeypatch.setenv("LITERATURE_EVIDENCE_NLI_MODEL_DIR", "/tmp/nli-test")
    def missing(pairs):
        raise ModuleNotFoundError("other package missing", name="missing-other")
    monkeypatch.setattr(nli, "scores_for_pairs", missing)
    with pytest.raises(ModuleNotFoundError):
        server.nli_assess_evidence("Hypothesis", "Evidence", "paper")


def test_missing_local_weight_file_is_not_a_verdict(monkeypatch):
    monkeypatch.setenv("LITERATURE_EVIDENCE_NLI_MODEL_DIR", "/tmp/nli-test")
    def missing(pairs):
        raise FileNotFoundError("model files missing")
    monkeypatch.setattr(nli, "scores_for_pairs", missing)
    out = server.nli_assess_evidence("Hypothesis", "Evidence", "paper")
    assert out["status"] == "LOCAL_MODEL_FILES_MISSING"
    assert out["verdict"] == "INSUFFICIENT_MODEL_EVIDENCE"


def test_evaluation_uses_local_configured_files_only(monkeypatch, tmp_path):
    nli._load_model.cache_clear()
    monkeypatch.delenv("LITERATURE_EVIDENCE_NLI_MODEL_DIR", raising=False)
    with pytest.raises(FileNotFoundError):
        nli._load_model()
    nli._load_model.cache_clear()
    monkeypatch.setenv("LITERATURE_EVIDENCE_NLI_MODEL_DIR", str(tmp_path))
    with pytest.raises(FileNotFoundError):
        nli._load_model()
    (tmp_path/"model.safetensors").write_bytes(b"fake model")
    nli._load_model.cache_clear()
    import hashlib
    expected = hashlib.sha256(b"fake model").hexdigest()
    monkeypatch.setattr(nli, "WEIGHTS_SHA256", expected)

    class MockModel:
        config = SimpleNamespace(id2label={0:"contradiction",1:"entailment",2:"neutral"})
        def to(self, device):
            self.device = device
            return self
        def eval(self):
            self.mode = "eval"
            return self

    model = MockModel()
    fake_transformers = SimpleNamespace(
        AutoTokenizer=SimpleNamespace(from_pretrained=lambda *a, **kw: "tok"),
        AutoModelForSequenceClassification=SimpleNamespace(from_pretrained=lambda *a, **kw: model),
    )
    fake_torch = SimpleNamespace(cuda=SimpleNamespace(is_available=lambda: True))
    monkeypatch.setattr(nli.importlib, "import_module",
                        lambda name: fake_transformers if name=="transformers" else fake_torch)
    monkeypatch.setenv("LITERATURE_EVIDENCE_NLI_DEVICE", "cpu")
    x=nli._load_model()
    assert x[0] == "tok" and x[3] == "cpu" and model.mode == "eval"
    nli._load_model.cache_clear()
    monkeypatch.setenv("LITERATURE_EVIDENCE_NLI_DEVICE", "invalid")
    with pytest.raises(ValueError, match="device"):
        nli._load_model()
    nli._load_model.cache_clear()
    monkeypatch.setenv("LITERATURE_EVIDENCE_NLI_DEVICE", "cuda")
    fake_torch.cuda.is_available=lambda: False
    with pytest.raises(ValueError, match="CUDA"):
        nli._load_model()
    nli._load_model.cache_clear()
    fake_torch.cuda.is_available=lambda: True
    assert nli._load_model()[3] == "cuda"
    nli._load_model.cache_clear()
    model.config.id2label = {0: "entailment", 1: "contradiction", 2: "neutral"}
    with pytest.raises(ValueError, match="label mapping"):
        nli._load_model()
    nli._load_model.cache_clear()


def test_cpu_batch_inference_uses_no_grad_and_three_logits(monkeypatch):
    class FakeTensor:
        def __init__(self, rows):
            self.rows=rows
        def to(self, device):
            assert device=="cpu"
            return self
        def cpu(self):
            return self
        def tolist(self):
            return self.rows

    class FakeTokenizer:
        def __call__(self, premises, hypotheses, **kwargs):
            assert all(p.startswith("Premise") for p in premises)
            assert all(h.startswith("Hypothesis") for h in hypotheses)
            assert kwargs["truncation"] and kwargs["max_length"]==512
            return {"input_ids":FakeTensor([[] for _ in premises])}

    class FakeModel:
        def __call__(self, **kwargs):
            return SimpleNamespace(logits=FakeTensor([[.1,.9,.0] for _ in kwargs["input_ids"].rows]))

    class FakeTorch:
        @staticmethod
        def inference_mode():
            return nullcontext()
        @staticmethod
        def softmax(logits, dim):
            assert dim==-1
            return logits

    monkeypatch.setattr(nli,"_load_model",lambda: (FakeTokenizer(),FakeModel(),FakeTorch(),"cpu"))
    outcomes=nli.scores_for_pairs([("Premise text","Hypothesis claim")]*17)
    assert len(outcomes)==17
    assert outcomes[-1]["entailment"]==.9



def test_tampered_local_model_weight_rejected_before_loading(monkeypatch, tmp_path):
    monkeypatch.setenv("LITERATURE_EVIDENCE_NLI_MODEL_DIR", str(tmp_path))
    (tmp_path / "model.safetensors").write_bytes(b"corrupt weights")
    nli._load_model.cache_clear()
    with pytest.raises(ValueError, match="SHA-256"):
        nli._load_model()
    nli._load_model.cache_clear()
