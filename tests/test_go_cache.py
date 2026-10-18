import json

import pytest

from literature_evidence_mcp import go_records


@pytest.mark.asyncio
async def test_fresh_cached_and_rate_limited(monkeypatch, tmp_path):
    monkeypatch.setenv("LITERATURE_EVIDENCE_CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(go_records.time, "time", lambda: 100.0)
    calls = []

    async def fake(query, limit, mode):
        calls.append((query, limit, mode))
        return {"status": "PROVIDER_RECORDS_ONLY_UNVERIFIED",
                "results": [{"source": "openalex", "records": [{"doi": "10.1/a"}]}]}

    monkeypatch.setattr(go_records, "go_probe_sources", fake)
    out = await go_records.go_cached_papers("research", 2)
    assert out["cache_status"] == "FRESH_UNVERIFIED_DATA"
    assert calls == [("research", 2, "records")]
    out = await go_records.go_cached_papers("research", 2)
    assert out["cache_status"] == "LOCAL_UNVERIFIED_CACHE"
    assert (await go_records.go_cached_papers("different", 2))["status"] == "LOCAL_RATE_LIMITED"
    monkeypatch.setattr(go_records.time, "time", lambda: 106.0)
    assert (await go_records.go_cached_papers("different", 2))["cache_status"] == "FRESH_UNVERIFIED_DATA"


@pytest.mark.asyncio
async def test_broken_cache_and_rate_file(monkeypatch, tmp_path):
    monkeypatch.setenv("LITERATURE_EVIDENCE_CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(go_records.time, "time", lambda: 200.0)

    async def fake(query, limit, mode):
        return {"status": "NATIVE_NOT_INSTALLED"}

    monkeypatch.setattr(go_records, "go_probe_sources", fake)
    (tmp_path / "last-request.txt").write_text("not-number")
    assert (await go_records.go_cached_papers("a-query", 1))["status"] == "NATIVE_NOT_INSTALLED"
    cache_files = list(tmp_path.glob("*.json"))
    assert cache_files == []
    (tmp_path / "last-request.txt").write_text("0")
    (tmp_path / (go_records.hashlib.sha256(json.dumps(["a-query", 1]).encode()).hexdigest() + ".json")).write_text("{broken")
    assert (await go_records.go_cached_papers("a-query", 1))["status"] == "NATIVE_NOT_INSTALLED"


@pytest.mark.asyncio
async def test_ttl_zero_and_large_payload_not_cached(monkeypatch, tmp_path):
    monkeypatch.setenv("LITERATURE_EVIDENCE_CACHE_DIR", str(tmp_path))
    clock = [100.0]
    monkeypatch.setattr(go_records.time, "time", lambda: clock[0])

    async def huge(query, limit, mode):
        return {"status": "PROVIDER_RECORDS_ONLY_UNVERIFIED", "data": "X" * 500_001}

    monkeypatch.setattr(go_records, "go_probe_sources", huge)
    first = await go_records.go_cached_papers("query", 2, 0)
    assert first["cache_status"] == "FRESH_UNVERIFIED_DATA"
    clock[0] = 110.0
    second = await go_records.go_cached_papers("query", 2, 3600)
    assert second["cache_status"] == "FRESH_UNVERIFIED_DATA"
    assert list(tmp_path.glob("*.json")) == []


@pytest.mark.parametrize("query,limit,ttl", [
    ("", 2, 10), ("a", 2, 10), (None, 2, 10),
    ("science", True, 10), ("science", 0, 10), ("science", 21, 10),
    ("science", 2, True), ("science", 2, -1), ("science", 2, 86401),
])
@pytest.mark.asyncio
async def test_reject_invalid(query, limit, ttl):
    with pytest.raises(ValueError):
        await go_records.go_cached_papers(query, limit, ttl)
