"""Only synthetic source fixtures; no publication of real corpus/gold material."""
from __future__ import annotations

import hashlib
import json
import sys
import warnings
import zipfile
from pathlib import Path

import pytest

from scripts.evaluation import pin_dual_track_candidate_sources as pinned


def fixture(tmp_path: Path, monkeypatch) -> tuple[Path, Path]:
    zpath = tmp_path / "retrieval.zip"
    jpath = tmp_path / "test.jsonl"
    records = pinned.CANDIDATES["retrieval"]["members"]
    with zipfile.ZipFile(zpath, "w") as f:
        for member in records:
            f.writestr(member, b"synthetic-case")
    jpath.write_bytes(b'{"synthetic": 1}\n{"synthetic": 2}\n')
    monkeypatch.setitem(pinned.CANDIDATES["retrieval"], "sha256",
                        hashlib.sha256(zpath.read_bytes()).hexdigest())
    monkeypatch.setitem(pinned.CANDIDATES["retrieval"], "md5",
                        hashlib.md5(zpath.read_bytes()).hexdigest())
    monkeypatch.setitem(pinned.CANDIDATES["classification"], "sha256",
                        hashlib.sha256(jpath.read_bytes()).hexdigest())
    monkeypatch.setitem(pinned.CANDIDATES["classification"], "size_bytes",
                        jpath.stat().st_size)
    return zpath, jpath


def test_source_audit_does_not_expose_content_or_make_superiority_claim(monkeypatch, tmp_path):
    a, b = fixture(tmp_path, monkeypatch)
    # Fixed source line-count gate is deliberately separate from integrity.
    raw = b.read_bytes()
    with pytest.raises(ValueError, match="line count"):
        pinned.verify(a, b)
    b.write_bytes(raw * 27598 + raw.splitlines(keepends=True)[0])
    monkeypatch.setitem(pinned.CANDIDATES["classification"], "sha256",
                        hashlib.sha256(b.read_bytes()).hexdigest())
    monkeypatch.setitem(pinned.CANDIDATES["classification"], "size_bytes",
                        b.stat().st_size)
    result = pinned.verify(a, b)
    assert result["status"].endswith("SCIENTIFIC_EVALUATION_NOT_RUN")
    assert result["datasets"]["retrieval"]["structural_count"] == 5
    assert result["datasets"]["classification"]["structural_count"] == 55197
    assert result["datasets"]["retrieval"]["gold_labels_inspected"] is False
    assert result["datasets"]["classification"]["blinding_confirmed"] is False
    assert result["scientific_superiority_demonstrated"] is False
    assert "synthetic-case" not in json.dumps(result)
    assert '"synthetic"' not in json.dumps(result)


def test_missing_and_tampered_external_file_fail_closed(monkeypatch, tmp_path):
    a, b = fixture(tmp_path, monkeypatch)
    with pytest.raises(FileNotFoundError):
        pinned.verify(tmp_path / "missing.zip", b)
    a.write_bytes(a.read_bytes() + b"tamper")
    with pytest.raises(ValueError, match="SHA-256"):
        pinned.verify(a, b)


def test_md5_is_source_agreement_gate_not_a_proof(monkeypatch, tmp_path):
    a, b = fixture(tmp_path, monkeypatch)
    monkeypatch.setitem(pinned.CANDIDATES["retrieval"], "md5", "0" * 32)
    with pytest.raises(ValueError, match="MD5"):
        pinned.verify(a, b)


def test_wrong_declared_size_fails_before_reading_labels(monkeypatch, tmp_path):
    a, b = fixture(tmp_path, monkeypatch)
    monkeypatch.setitem(pinned.CANDIDATES["classification"], "size_bytes", 1)
    with pytest.raises(ValueError, match="size mismatch"):
        pinned.verify(a, b)


@pytest.mark.parametrize("bad_members", [
    ["nfcorpus/corpus.jsonl"], ["../evil"],
    ["nfcorpus/../evil"], ["nfcorpus\\evil"],
    ["nfcorpus/corpus.jsonl", "nfcorpus/corpus.jsonl"],
])
def test_no_wrong_duplicate_or_dangerous_archive_paths(monkeypatch, tmp_path, bad_members):
    a, b = fixture(tmp_path, monkeypatch)
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="Duplicate name:", category=UserWarning)
        with zipfile.ZipFile(a, "w") as file:
            for name in bad_members:
                file.writestr(name, b"private-synthetic")
    monkeypatch.setitem(pinned.CANDIDATES["retrieval"], "sha256",
                        hashlib.sha256(a.read_bytes()).hexdigest())
    monkeypatch.setitem(pinned.CANDIDATES["retrieval"], "md5",
                        hashlib.md5(a.read_bytes()).hexdigest())
    with pytest.raises(ValueError, match="member|Unsafe|duplicate"):
        pinned.verify(a, b)


def test_verifier_cli_writes_summary_without_gold(monkeypatch, tmp_path, capsys):
    a, b = fixture(tmp_path, monkeypatch)
    b.write_bytes(b'{"synthetic": 1}\n' * 55197)
    monkeypatch.setitem(pinned.CANDIDATES["classification"], "sha256",
                        hashlib.sha256(b.read_bytes()).hexdigest())
    monkeypatch.setitem(pinned.CANDIDATES["classification"], "size_bytes",
                        b.stat().st_size)
    target = tmp_path / "summaries" / "metadata.json"
    monkeypatch.setattr(sys, "argv", [
        "cli", "--retrieval-zip", str(a), "--classification-jsonl", str(b),
        "--output", str(target),
    ])
    pinned.main()
    data = json.loads(target.read_text())
    assert not data["scientific_superiority_demonstrated"]
    assert data["datasets"]["classification"]["integrity_status"] == "BYTE_PIN_VERIFIED"
    assert "NO_GOLD_READ" in capsys.readouterr().out
