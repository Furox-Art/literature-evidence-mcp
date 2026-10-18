"""Deterministic tests for unavailable, invalid and successful native adapters."""
import asyncio
import json
from types import SimpleNamespace

import pytest

from literature_evidence_mcp import native, server


def module_or_missing(monkeypatch, name, fake):
    original = native.importlib.import_module

    def get(module):
        if module == name:
            if fake is None:
                raise ModuleNotFoundError(f"no module named {name}", name=name)
            if fake == "nested_missing":
                raise ModuleNotFoundError("transitive missing", name="transitive")
            return fake
        return original(module)

    monkeypatch.setattr(native.importlib, "import_module", get)


def test_rust_absent_and_present(monkeypatch):
    module_or_missing(monkeypatch, "literature_evidence_rust", None)
    assert native.rust_locate("The study was randomized.", "randomized")["status"] == (
        "NATIVE_NOT_INSTALLED")
    module_or_missing(monkeypatch, "literature_evidence_rust",
                      SimpleNamespace(find_quote=lambda text, quote: (14, 24)))
    result = server.rust_locate_quote("The study was randomized.", "randomized")
    assert result["status"] == "TEXTUAL_MATCH_ONLY"
    assert (result["offset_start"], result["offset_end"]) == (14, 24)
    assert result["semantic_support_verified"] is False
    module_or_missing(monkeypatch, "literature_evidence_rust",
                      SimpleNamespace(find_quote=lambda text, quote: None))
    assert native.rust_locate("some text", "missing")["offset_start"] is None
    assert native.rust_locate("some text", "missing")["status"] == "NOT_VERIFIED"


@pytest.mark.parametrize("text,quote", [
    ("", "valid"), ("x" * 250001, "valid"), (None, "valid"),
    ("data", ""), ("data", " " * 5), ("data", "z" * 2501),
    ("data", None),
])
def test_rust_invalid(text, quote):
    with pytest.raises(ValueError):
        native.rust_locate(text, quote)


def test_rust_dependency_error_does_not_masquerade_as_missing(monkeypatch):
    module_or_missing(monkeypatch, "literature_evidence_rust", "nested_missing")
    with pytest.raises(ModuleNotFoundError, match="transitive"):
        native.rust_locate("hello", "hello")


def test_cpp_present_missing_and_reject_input(monkeypatch):
    example = [{"estimate": 1.0, "standard_error": 0.5},
               {"estimate": 2.0, "standard_error": 0.25}]
    module_or_missing(monkeypatch, "literature_evidence_cpp", None)
    assert native.cpp_fixed_effect_meta_analysis(example)["status"] == (
        "NATIVE_NOT_INSTALLED")
    module_or_missing(monkeypatch, "literature_evidence_cpp",
                      SimpleNamespace(fixed_effect=lambda pairs: {
                          "pooled_estimate": 1.8, "scientific_validity_assessed": False,
                          "observed_pairs": pairs,
                      }))
    result = server.cpp_fixed_effect_meta(example)
    assert result["status"] == "NUMERICAL_CALCULATION_ONLY"
    assert result["pooled_estimate"] == 1.8
    assert result["observed_pairs"] == [(1.0, 0.5), (2.0, 0.25)]
    assert result["scientific_validity_assessed"] is False
    module_or_missing(monkeypatch, "literature_evidence_cpp", "nested_missing")
    with pytest.raises(ModuleNotFoundError):
        native.cpp_fixed_effect_meta_analysis(example)


@pytest.mark.parametrize("records", [
    [], [{}], ["bad", {}], None,
    [{"estimate": True, "standard_error": 1}, {"estimate": 1, "standard_error": 2}],
    [{"estimate": 1, "standard_error": "invalid"}, {"estimate": 2, "standard_error": 1}],
    [{"estimate": 1, "standard_error": 1}, {"estimate": 2, "standard_error": None}],
])
def test_cpp_invalid(records):
    with pytest.raises((ValueError, TypeError)):
        native.cpp_fixed_effect_meta_analysis(records)


@pytest.mark.asyncio
async def test_go_missing_and_valid(monkeypatch):
    monkeypatch.delenv("LITERATURE_EVIDENCE_GO_BIN", raising=False)
    assert (await server.go_parallel_provider_status("research", 1))["status"] == (
        "NATIVE_NOT_INSTALLED")
    monkeypatch.setenv("LITERATURE_EVIDENCE_GO_BIN", "/path/to/go")
    class Proc:
        returncode = 0

        async def communicate(self, data):
            assert json.loads(data)["query"] == "research"
            return (b'{"status":"PROVIDER_STATUS_ONLY","results":[]}', b"")

    async def launch(*args, **kwargs):
        assert args == ("/path/to/go",)
        assert kwargs["stdin"] == asyncio.subprocess.PIPE
        return Proc()

    monkeypatch.setattr(native.asyncio, "create_subprocess_exec", launch)
    out = await native.go_probe_sources("research", 1)
    assert out["status"] == "PROVIDER_STATUS_ONLY"
    assert out["backend"] == "Go"


@pytest.mark.parametrize("query,limit", [
    ("", 5), ("x", 5), ("a" * 501, 5), (None, 5),
    ("research", 0), ("research", 21), ("research", True), ("research", 1.5),
])
@pytest.mark.asyncio
async def test_go_bad_inputs(query, limit):
    with pytest.raises(ValueError):
        await native.go_probe_sources(query, limit)


@pytest.mark.asyncio
async def test_go_launch_failure(monkeypatch):
    monkeypatch.setenv("LITERATURE_EVIDENCE_GO_BIN", "/notfound")
    async def launch(*args, **kwargs):
        raise FileNotFoundError("not found")

    monkeypatch.setattr(native.asyncio, "create_subprocess_exec", launch)
    out = await native.go_probe_sources("query", 1)
    assert out["status"] == "NATIVE_EXECUTION_FAILED"


@pytest.mark.parametrize("output,code,expected", [
    (b"{}", 2, "NATIVE_EXECUTION_FAILED"),
    (b"x" * 65537, 0, "NATIVE_INVALID_RESPONSE"),
    (b"bad json", 0, "NATIVE_INVALID_RESPONSE"),
    (b"[]", 0, "NATIVE_INVALID_RESPONSE"),
    (b'{"status":"unexpected"}', 0, "NATIVE_INVALID_RESPONSE"),
    (b'{"status":"PROVIDER_STATUS_ONLY"}', 0, "PROVIDER_STATUS_ONLY"),
])
@pytest.mark.asyncio
async def test_go_untrusted_outputs(monkeypatch, output, code, expected):
    monkeypatch.setenv("LITERATURE_EVIDENCE_GO_BIN", "/tmp/go")
    class Proc:
        returncode = code

        async def communicate(self, request):
            assert json.loads(request)["limit"] == 2
            return output, b"private error never surfaced"

    async def launch(*args, **kwargs):
        return Proc()

    monkeypatch.setattr(native.asyncio, "create_subprocess_exec", launch)
    out = await native.go_probe_sources("query", 2)
    assert out["status"] == expected
    assert "private error" not in json.dumps(out)


@pytest.mark.asyncio
async def test_go_timeout(monkeypatch):
    monkeypatch.setenv("LITERATURE_EVIDENCE_GO_BIN", "/tmp/go")
    class Proc:
        killed = False

        async def communicate(self, data):
            await asyncio.sleep(0)

        def kill(self):
            self.killed = True

        async def wait(self):
            assert self.killed
            return 1

    proc = Proc()

    async def launch(*args, **kwargs):
        return proc

    async def fake_wait_for(awaitable, timeout):
        await awaitable
        raise TimeoutError()

    monkeypatch.setattr(native.asyncio, "create_subprocess_exec", launch)
    monkeypatch.setattr(native.asyncio, "wait_for", fake_wait_for)
    assert (await native.go_probe_sources("query"))["status"] == "NATIVE_TIMEOUT"
    assert proc.killed is True
