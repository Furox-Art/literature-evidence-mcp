"""Opt-in C++ DL adapter error and absence cases, all without fake claims."""
from types import SimpleNamespace

import pytest

from literature_evidence_mcp import native, server

DATA = [{"estimate": 1., "standard_error": .2},
        {"estimate": 2., "standard_error": .3},
        {"estimate": 3., "standard_error": .4},
        {"estimate": 1.5, "standard_error": .5}]


@pytest.mark.parametrize("input_data,loo,error", [
    ([], False, ValueError), (None, False, ValueError),
    (DATA[:2], False, ValueError), (DATA, "true", TypeError),
    (DATA[:3], True, ValueError),
    ([None] + DATA, False, TypeError),
    ([{"estimate": True, "standard_error": 1}] + DATA, False, TypeError),
])
def test_cpp_refuses_unjustified_inputs(input_data, loo, error):
    with pytest.raises(error):
        server.cpp_random_effects(input_data, loo)


def test_cpp_extension_unavailable_and_internal_dependency(monkeypatch):
    original = native.importlib.import_module
    def missing(key):
        if key == "literature_evidence_cpp":
            raise ModuleNotFoundError("not found", name=key)
        return original(key)
    monkeypatch.setattr(native.importlib, "import_module", missing)
    assert server.cpp_random_effects(DATA)["status"] == "NATIVE_NOT_INSTALLED"
    def transitive(key):
        raise ModuleNotFoundError("nested missing", name="numpy")
    monkeypatch.setattr(native.importlib, "import_module", transitive)
    with pytest.raises(ModuleNotFoundError, match="nested"):
        native.cpp_random_effects_meta(DATA)


def test_cpp_extension_outputs_and_loo(monkeypatch):
    fake = SimpleNamespace(
        random_effects_dl=lambda rows: {"pooled_estimate": 1.1,
                                        "scientific_validity_assessed": False},
        leave_one_out_dl=lambda rows: [{"excluded_study_index": i} for i in range(len(rows))],
    )
    original = native.importlib.import_module
    monkeypatch.setattr(native.importlib, "import_module",
                        lambda key: fake if key == "literature_evidence_cpp" else original(key))
    no_loo = server.cpp_random_effects(DATA)
    assert no_loo["pooled_estimate"] == 1.1
    assert no_loo["status"] == "NUMERICAL_CALCULATION_ONLY"
    assert "leave_one_out" not in no_loo
    with_loo = server.cpp_random_effects(DATA, True)
    assert [v["excluded_study_index"] for v in with_loo["leave_one_out"]] == list(range(4))


@pytest.mark.asyncio
async def test_go_records_mcp_tool(monkeypatch):
    async def fake(query, limit, ttl):
        assert (query, limit, ttl) == ("science", 2, 20)
        return {"status": "PROVIDER_RECORDS_ONLY_UNVERIFIED"}
    monkeypatch.setattr(server, "go_cached_papers", fake)
    out = await server.go_literature_records("science", 2, 20)
    assert out["status"] == "PROVIDER_RECORDS_ONLY_UNVERIFIED"


@pytest.mark.asyncio
async def test_go_native_records_mode_validation(monkeypatch):
    from literature_evidence_mcp import native
    monkeypatch.setenv("LITERATURE_EVIDENCE_GO_BIN", "mock")
    class P:
        returncode = 0
        async def communicate(self, data):
            import json
            assert json.loads(data)["mode"] == "records"
            return b'{"status":"PROVIDER_RECORDS_ONLY_UNVERIFIED","results":[]}', b""
    async def spawn(*args, **kwargs):
        return P()
    monkeypatch.setattr(native.asyncio, "create_subprocess_exec", spawn)
    result = await native.go_probe_sources("research", 2, mode="records")
    assert result["status"] == "PROVIDER_RECORDS_ONLY_UNVERIFIED"
    with pytest.raises(ValueError):
        await native.go_probe_sources("research", 2, mode="unknown")
