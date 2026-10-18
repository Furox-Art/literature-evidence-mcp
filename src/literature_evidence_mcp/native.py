"""Opt-in native modules: no silent substitution or scientific validity claims."""
from __future__ import annotations

import asyncio
import importlib
import json
import os


def rust_locate(source_text: str, quote: str) -> dict:
    """Locate literal quote using PyO3; char offsets never imply semantic support."""
    if not isinstance(source_text, str) or not 1 <= len(source_text) <= 250_000:
        raise ValueError("source_text must contain 1-250000 characters")
    if not isinstance(quote, str) or not 1 <= len(quote.strip()) <= 2500:
        raise ValueError("quote must contain 1-2500 nonblank characters")
    try:
        extension = importlib.import_module("literature_evidence_rust")
    except ModuleNotFoundError as exc:
        if exc.name != "literature_evidence_rust":
            raise
        return {"status": "NATIVE_NOT_INSTALLED", "backend": "Rust"}
    span = extension.find_quote(source_text, quote)
    return {
        "status": "TEXTUAL_MATCH_ONLY" if span is not None else "NOT_VERIFIED",
        "backend": "Rust",
        "offset_start": span[0] if span is not None else None,
        "offset_end": span[1] if span is not None else None,
        "semantic_support_verified": False,
    }


def cpp_fixed_effect_meta_analysis(studies: list[dict]) -> dict:
    """Numerical fixed-effect inverse-variance pooling; assumes valid supplied estimates."""
    if not isinstance(studies, list):
        raise TypeError("studies must be a list")
    if not 2 <= len(studies) <= 10_000:
        raise ValueError("2-10000 study estimates are required")
    pairs = []
    for study in studies:
        if not isinstance(study, dict):
            raise TypeError("Each study must contain estimate and standard_error")
        estimate, se = study.get("estimate"), study.get("standard_error")
        if (isinstance(estimate, bool) or isinstance(se, bool)
                or not isinstance(estimate, (int, float))
                or not isinstance(se, (int, float))):
            raise TypeError("estimate and standard_error must be numeric")
        pairs.append((float(estimate), float(se)))
    try:
        extension = importlib.import_module("literature_evidence_cpp")
    except ModuleNotFoundError as exc:
        if exc.name != "literature_evidence_cpp":
            raise
        return {"status": "NATIVE_NOT_INSTALLED", "backend": "C++",
                "scientific_validity_assessed": False}
    result = dict(extension.fixed_effect(pairs))
    result["status"] = "NUMERICAL_CALCULATION_ONLY"
    result["backend"] = "C++"
    return result


def cpp_random_effects_meta(studies: list[dict], leave_one_out: bool = False) -> dict:
    """Optional C++ DL estimator and leave-one-out, without study eligibility judgments."""
    if not isinstance(studies, list) or not 3 <= len(studies) <= 10000:
        raise ValueError("3-10000 study records required")
    if not isinstance(leave_one_out, bool):
        raise TypeError("leave_one_out must be boolean")
    pairs = []
    for study in studies:
        if not isinstance(study, dict):
            raise TypeError("Study must be an object")
        effect, se = study.get("estimate"), study.get("standard_error")
        if isinstance(effect, bool) or isinstance(se, bool) or not isinstance(effect, (int, float)) or not isinstance(se, (int, float)):
            raise TypeError("Numeric estimates and SEs required")
        pairs.append((float(effect), float(se)))
    if leave_one_out and not 4 <= len(pairs) <= 1000:
        raise ValueError("Leave-one-out requires 4-1000 studies")
    try:
        extension = importlib.import_module("literature_evidence_cpp")
    except ModuleNotFoundError as exc:
        if exc.name != "literature_evidence_cpp":
            raise
        return {"status": "NATIVE_NOT_INSTALLED", "backend": "C++",
                "scientific_validity_assessed": False}
    result = dict(extension.random_effects_dl(pairs))
    if leave_one_out:
        result["leave_one_out"] = [dict(r) for r in extension.leave_one_out_dl(pairs)]
    result["status"] = "NUMERICAL_CALCULATION_ONLY"
    result["backend"] = "C++"
    return result



async def go_probe_sources(query: str, limit: int = 5, mode: str = "status") -> dict:
    """Run optional Go subprocess with fixed provider URLs. No raw articles are stored."""
    if not isinstance(query, str) or not 2 <= len(query.strip()) <= 500:
        raise ValueError("query must contain 2-500 characters")
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 20:
        raise ValueError("limit must be an integer 1-20")
    if mode not in {"status", "records"}:
        raise ValueError("Unsupported Go mode")
    binary = os.environ.get("LITERATURE_EVIDENCE_GO_BIN")
    if not binary:
        return {"status": "NATIVE_NOT_INSTALLED", "backend": "Go"}
    try:
        proc = await asyncio.create_subprocess_exec(
            binary, stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
    except OSError:
        return {"status": "NATIVE_EXECUTION_FAILED", "backend": "Go"}
    request = json.dumps({"query": query, "limit": limit, "mode": mode}).encode("utf-8")
    try:
        stdout, _ = await asyncio.wait_for(proc.communicate(request), timeout=20)
    except TimeoutError:
        proc.kill()
        await proc.wait()
        return {"status": "NATIVE_TIMEOUT", "backend": "Go"}
    if proc.returncode != 0:
        return {"status": "NATIVE_EXECUTION_FAILED", "backend": "Go"}
    if len(stdout) > 65536:
        return {"status": "NATIVE_INVALID_RESPONSE", "backend": "Go"}
    try:
        payload = json.loads(stdout)
    except (ValueError, UnicodeDecodeError):
        return {"status": "NATIVE_INVALID_RESPONSE", "backend": "Go"}
    expected = ("PROVIDER_RECORDS_ONLY_UNVERIFIED" if mode == "records"
                else "PROVIDER_STATUS_ONLY")
    if not isinstance(payload, dict) or payload.get("status") != expected:
        return {"status": "NATIVE_INVALID_RESPONSE", "backend": "Go"}
    return {**payload, "backend": "Go"}
