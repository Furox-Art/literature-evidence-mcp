import math

from literature_evidence_mcp import server


def test_real_cpp_against_analytic_two_study_reference():
    data = [{"estimate": 1.0, "standard_error": 0.5},
            {"estimate": 2.0, "standard_error": 0.5}]
    r = server.cpp_fixed_effect_meta(data)
    assert r["status"] == "NUMERICAL_CALCULATION_ONLY"
    assert r["backend"] == "C++"
    assert math.isclose(r["pooled_estimate"], 1.5, rel_tol=1e-12)
    assert math.isclose(r["standard_error"], math.sqrt(0.125), rel_tol=1e-12)
    assert r["ci95_lower"] < 1.5 < r["ci95_upper"]
    assert r["scientific_validity_assessed"] is False
