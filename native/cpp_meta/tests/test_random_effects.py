"""Independent analytic reference checks and adversarial numerical inputs."""
import math

import pytest
from literature_evidence_cpp import leave_one_out_dl, random_effects_dl


def python_reference(values):
    k = len(values)
    w = [1 / (se * se) for _, se in values]
    mean = sum(a * b[0] for a, b in zip(w, values)) / sum(w)
    q = sum(a * ((b[0] - mean)**2) for a, b in zip(w, values))
    c = sum(w) - sum(a*a for a in w) / sum(w)
    tau2 = max(0, (q - k + 1) / c)
    rw = [1 / (se * se + tau2) for _, se in values]
    pooled = sum(a * b[0] for a, b in zip(rw, values)) / sum(rw)
    return pooled, tau2, q, max(0, 100*(q-k+1)/q) if q else 0


@pytest.mark.parametrize("values", [
    [(1.0, .2), (2.0, .3), (3.0, .4)],
    [(1.0, .3), (1.0, .3), (1.0, .3)],
    [(.1, 2), (-.4, 1.5), (.2, 1), (.8, 1.2)],
])
def test_dl_against_independent_python_formula(values):
    expected = python_reference(values)
    out = random_effects_dl(values)
    for key, target in zip(("pooled_estimate", "tau_squared", "q", "i_squared_percent"), expected):
        assert math.isclose(out[key], target, abs_tol=1e-11)
    assert out["ci95_lower"] < out["ci95_upper"]
    assert out["approx_prediction95_lower"] < out["approx_prediction95_upper"]
    assert out["scientific_validity_assessed"] is False


def test_leave_one_out_reproduces_manual_subset_fits():
    inp = [(1., .2), (2., .3), (3., .4), (4., .5)]
    results = leave_one_out_dl(inp)
    assert len(results) == len(inp)
    for n, record in enumerate(results):
        assert record["excluded_study_index"] == n
        without = inp[:n] + inp[n + 1:]
        assert math.isclose(record["pooled_estimate"], random_effects_dl(without)["pooled_estimate"])


@pytest.mark.parametrize("values", [
    [], [(1., .3)], [(1., .3), (2., .4)],
    [(1., 0), (2., .3), (3., .4)],
    [(float("nan"), .2), (2., .3), (3., .4)],
    [(1., float("inf")), (2., .3), (3., .4)],
    [(1e308, 1e-200), (2., 1.), (3., 1.)],
    [(1e308, .4), (-1e308, .4), (2., .5)],
    [(1., 1e-200), (2., 1.), (3., 1.)],
])
def test_invalid_random_effects(values):
    with pytest.raises(ValueError):
        random_effects_dl(values)


@pytest.mark.parametrize("values", [[], [(1., .3), (2., .4), (3., .5)],
                                    [(1., .3), (2., .4), (3., 0), (4., .5)]])
def test_invalid_loo(values):
    with pytest.raises(ValueError):
        leave_one_out_dl(values)

def test_large_weights_are_refused_without_silent_numeric_corruption():
    with pytest.raises(ValueError, match="weight sums"):
        random_effects_dl([(1., 1e-100), (2., 1e-100), (3., 1e-100)])


def test_overflowing_q_is_refused():
    with pytest.raises(ValueError, match="heterogeneity denominator"):
        random_effects_dl([(1e120, 1e-60), (0., 1e-60), (-1e120, 1e-60)])
