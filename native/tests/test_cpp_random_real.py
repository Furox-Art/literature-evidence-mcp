"""End-to-end invocation through the genuine compiled C++ binding."""
import math

from literature_evidence_mcp import server


def test_native_dl_model_and_leave_one_out():
    studies = [{"estimate": effect, "standard_error": se}
               for effect, se in [(1., .2), (2., .3), (3., .4), (1.5, .5)]]
    result = server.cpp_random_effects(studies, True)
    assert result["status"] == "NUMERICAL_CALCULATION_ONLY"
    assert result["method"] == "DERSIMONIAN_LAIRD_RANDOM_EFFECTS"
    assert result["tau_squared"] >= 0
    assert 0 <= result["i_squared_percent"] <= 100
    assert math.isfinite(result["q"])
    assert len(result["leave_one_out"]) == len(studies)
    assert result["scientific_validity_assessed"] is False
