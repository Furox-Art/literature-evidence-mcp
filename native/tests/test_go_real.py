import pytest
from literature_evidence_mcp import server

@pytest.mark.asyncio
async def test_real_go_worker_concurrent_provider_status():
    status = await server.go_parallel_provider_status("neural data", 1)
    assert status["status"] == "PROVIDER_STATUS_ONLY"
    assert status["backend"] == "Go"
    assert [row["source"] for row in status["results"]] == [
        "crossref", "openalex", "europepmc",
    ]
    assert all(isinstance(row["http_status"], int) for row in status["results"])
    assert "not" in status["notice"].lower()
