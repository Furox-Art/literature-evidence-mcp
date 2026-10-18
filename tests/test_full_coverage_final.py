"""Complete remaining runnable paths without coverage suppression."""
from __future__ import annotations

import csv
import hashlib
import json
import runpy
import sys
from pathlib import Path

import httpx
import pytest

from literature_evidence_mcp import benchmark, server
from literature_evidence_mcp.core import (
    CROSSREF,
    EvidenceLedger,
    ProviderError,
    ResearchClient,
    evidence_graph,
)
from literature_evidence_mcp.methodology import audit_methodology_evidence


@pytest.mark.asyncio
async def test_provider_retry_exhaustion_is_explicit(monkeypatch):
    async def no_sleep(_):
        return None

    monkeypatch.setattr("literature_evidence_mcp.core.asyncio.sleep", no_sleep)
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(503)
    async with (httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http,
                ResearchClient(http) as researcher):
        with pytest.raises(ProviderError, match="retry limit"):
            await researcher._get(CROSSREF, "/works")
    assert len(calls) == 3


def test_malformed_graph_edge_and_metadata():
    with pytest.raises(ValueError, match="existing nodes"):
        evidence_graph([{"id": "a"}], [{"source": "a", "target": "bad",
                                        "evidence_id": "doi:10.1000/test"}])


@pytest.mark.asyncio
async def test_invalid_ledger_payload_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="object"):
        await EvidenceLedger(tmp_path / "ledger.jsonl").append("record", [])


def test_max_annotation_input_is_checked():
    with pytest.raises(ValueError, match="100"):
        audit_methodology_evidence("study", "outcome", "randomized_trial",
                                   "data", [{"domain": "sequence_generation",
                                             "answer": "unclear"}] * 101)


def test_benchmark_filters_subthreshold_fragment(tmp_path, monkeypatch):
    p = tmp_path / "fixture.csv"
    rows = [{
        "paper_id": "p1",
        "paper_parse": json.dumps({"pdf_parse": {"body_text": [
            {"text": "The sample consisted of randomly allocated controls."}]}}),
        "manual_assessment": json.dumps([{"result": [{
            "rationale_text_quote": (
                '"The sample consisted of randomly allocated controls." '
                'Reviewer also noted "four completely unremarkable words".'
            )}]}]),
        "roboto2_assessment": "null",
    }]
    with p.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0])
        writer.writeheader()
        writer.writerows(rows)
    monkeypatch.setattr(benchmark, "DATA_SHA256",
                        hashlib.sha256(p.read_bytes()).hexdigest())
    records = benchmark.load_records(p)
    assert len(records) == 1
    assert records[0]["fragments"] == [
        "The sample consisted of randomly allocated controls."]


def test_benchmark_cli_stdout_without_output_path(tmp_path, monkeypatch, capsys):
    p = tmp_path / "fixture.csv"
    with p.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["paper_id", "paper_parse", "manual_assessment",
                         "roboto2_assessment"])
        writer.writerow(["p1", "null", "[]", "null"])
    monkeypatch.setattr(benchmark, "DATA_SHA256",
                        hashlib.sha256(p.read_bytes()).hexdigest())
    monkeypatch.setattr(sys, "argv", ["bench", str(p)])
    benchmark.main()
    assert '"evaluated_papers": 0' in capsys.readouterr().out


def test_server_main_invalid_and_normal_transports(monkeypatch):
    calls = []
    def fake_run(self, *args, **kwargs):
        calls.append((args, kwargs))
    monkeypatch.setattr(type(server.mcp), "run", fake_run)
    monkeypatch.setenv("MCP_TRANSPORT", "broken")
    with pytest.raises(ValueError, match="MCP_TRANSPORT"):
        server.main()
    monkeypatch.setenv("MCP_TRANSPORT", "stdio")
    server.main()
    assert calls[-1] == ((), {})
    monkeypatch.setenv("MCP_TRANSPORT", "streamable-http")
    monkeypatch.setenv("MCP_PORT", "8765")
    server.main()
    assert calls[-1][1]["transport"] == "streamable-http"
    assert calls[-1][1]["host"] == "127.0.0.1"
    assert calls[-1][1]["port"] == 8765


def test_server_direct_entrypoint_invokes_main(monkeypatch):
    calls = []
    monkeypatch.setattr(type(server.mcp), "run",
                        lambda self, *args, **kwargs: calls.append((args, kwargs)))
    monkeypatch.setenv("MCP_TRANSPORT", "stdio")
    runpy.run_path(str(Path(server.__file__)), run_name="__main__")
    assert len(calls) == 1
