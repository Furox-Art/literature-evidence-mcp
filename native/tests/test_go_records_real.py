"""Actual Go subprocess with bounded real provider metadata (may be offline)."""
import pytest

from literature_evidence_mcp import server


@pytest.mark.asyncio
async def test_go_native_records_are_unverified_and_never_claim_completeness(tmp_path, monkeypatch):
    monkeypatch.setenv("LITERATURE_EVIDENCE_CACHE_DIR", str(tmp_path))
    output = await server.go_literature_records("neurobiology", 2)
    assert output["status"] == "PROVIDER_RECORDS_ONLY_UNVERIFIED"
    assert output["cache_status"] == "FRESH_UNVERIFIED_DATA"
    assert len(output["results"]) == 3
    assert all(item["source"] in {"crossref", "openalex", "europepmc"} for item in output["results"])
    assert all(len(item.get("records", [])) <= 2 for item in output["results"])
    cached = await server.go_literature_records("neurobiology", 2)
    assert cached["cache_status"] == "LOCAL_UNVERIFIED_CACHE"
