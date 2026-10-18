"""Machine-specific optional microbenchmarks, never evidence of scientific superiority."""
from __future__ import annotations

import importlib
import json
import time

from literature_evidence_mcp.methodology import _locate


def measure(callback, n=1000):
    start = time.perf_counter()
    for _ in range(n):
        callback()
    return round((time.perf_counter() - start) / n * 1e6, 3)


def main():
    text = "αβ " + "scientific trial " * 100 + "statistically significant effect"
    quote = "statistically significant"
    results = {"platform_specific": True, "iterations": 1000,
               "metric": "microseconds_per_operation_not_scientific_accuracy",
               "python_literal_match_us": measure(lambda: _locate(text, quote))}
    try:
        rust = importlib.import_module("literature_evidence_rust")
    except ModuleNotFoundError:
        results["rust_status"] = "NOT_INSTALLED"
    else:
        assert rust.find_quote(text, quote) == _locate(text, quote)
        results["rust_literal_match_us"] = measure(lambda: rust.find_quote(text, quote))
        results["rust_python_output_equivalent"] = True
    try:
        cpp = importlib.import_module("literature_evidence_cpp")
    except ModuleNotFoundError:
        results["cpp_status"] = "NOT_INSTALLED"
    else:
        studies = [(1.0, 0.2), (2.0, 0.3), (1.5, 0.5), (2.2, 0.4)]
        result = cpp.random_effects_dl(studies)
        assert result["scientific_validity_assessed"] is False
        results["cpp_dl_calculation_us"] = measure(lambda: cpp.random_effects_dl(studies))
        results["cpp_result_checked_for_numeric_finiteness"] = True
    results["note"] = ("Warm same-machine microbenchmarks only. Go network latency, "
                       "C++ vs Python statistical equivalence and comparative scientific "
                       "search precision are NOT evaluated by this script.")
    print(json.dumps(results, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
