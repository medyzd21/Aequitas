"""Tests for engine.fairness_stress."""
from __future__ import annotations

import numpy as np
import pytest

from engine.fairness_stress import (
    build_cohort_betas,
    stochastic_cohort_stress,
    summary_frame,
)


def _toy_valuation() -> dict:
    return {
        1960: {"epv_contributions": 100.0, "epv_benefits": 115.0,
               "money_worth_ratio": 1.15, "members": 2},
        1970: {"epv_contributions": 200.0, "epv_benefits": 210.0,
               "money_worth_ratio": 1.05, "members": 3},
        1980: {"epv_contributions": 150.0, "epv_benefits": 150.0,
               "money_worth_ratio": 1.00, "members": 3},
        1990: {"epv_contributions": 100.0, "epv_benefits": 90.0,
               "money_worth_ratio": 0.90, "members": 2},
    }


def test_build_cohort_betas_signs():
    betas = build_cohort_betas([1960, 1970, 1980, 1990], slope=0.5)
    # reference year is the mean = 1975
    assert betas[1960] > 0   # older — positive exposure
    assert betas[1990] < 0   # younger — negative exposure
    # and symmetric around the reference
    assert abs(abs(betas[1960]) - abs(betas[1990])) < 1e-9


def test_build_cohort_betas_zero_slope():
    betas = build_cohort_betas([1960, 1990], slope=0.0)
    assert all(v == 0.0 for v in betas.values())


def test_stress_shapes_and_keys():
    r = stochastic_cohort_stress(_toy_valuation(), n_scenarios=500, seed=1)
    for key in (
        "mean_gini", "p95_gini", "mean_index", "p05_index",
        "corridor_pass_rate", "worst_cohort_freq",
        "youngest_cohort", "youngest_poor_rate",
        "mwr_samples_df", "gini_series", "index_series",
    ):
        assert key in r
    assert r["mwr_samples_df"].shape == (500, 4)
    assert r["gini_series"].shape == (500,)
    assert r["index_series"].shape == (500,)
    # worst cohort frequencies are a probability distribution
    total = sum(r["worst_cohort_freq"].values())
    assert abs(total - 1.0) < 1e-9


def test_stress_determinism_seed():
    r1 = stochastic_cohort_stress(_toy_valuation(), n_scenarios=300, seed=7)
    r2 = stochastic_cohort_stress(_toy_valuation(), n_scenarios=300, seed=7)
    assert np.allclose(r1["gini_series"], r2["gini_series"])
    assert np.allclose(r1["index_series"], r2["index_series"])


def test_stress_zero_sigma_collapses_to_baseline():
    # No randomness → every scenario is the baseline → Gini is constant
    r = stochastic_cohort_stress(
        _toy_valuation(),
        n_scenarios=100,
        factor_sigma=0.0,
        idiosyncratic_sigma=0.0,
        seed=0,
    )
    # all rows identical → gini std ≈ 0
    assert r["gini_series"].std() < 1e-12
    assert r["index_series"].std() < 1e-12
    assert r["corridor_pass_rate"] in (0.0, 1.0)


def test_pass_rate_in_unit_interval():
    r = stochastic_cohort_stress(_toy_valuation(), n_scenarios=500, seed=3)
    assert 0.0 <= r["corridor_pass_rate"] <= 1.0
    assert 0.0 <= r["youngest_poor_rate"] <= 1.0


def test_worst_cohort_freq_labels_are_cohorts():
    r = stochastic_cohort_stress(_toy_valuation(), n_scenarios=200, seed=5)
    assert set(r["worst_cohort_freq"].keys()) == {1960, 1970, 1980, 1990}


def test_summary_frame_shape():
    r = stochastic_cohort_stress(_toy_valuation(), n_scenarios=100, seed=2)
    sf = summary_frame(r)
    assert list(sf.columns) == ["metric", "value"]
    assert len(sf) >= 7


def test_higher_sigma_raises_dispersion():
    r_low = stochastic_cohort_stress(
        _toy_valuation(), n_scenarios=1_000,
        factor_sigma=0.02, idiosyncratic_sigma=0.0, seed=11,
    )
    r_high = stochastic_cohort_stress(
        _toy_valuation(), n_scenarios=1_000,
        factor_sigma=0.20, idiosyncratic_sigma=0.0, seed=11,
    )
    # wider macro shock → wider Gini distribution
    assert r_high["gini_series"].std() > r_low["gini_series"].std()
    # and worse p95
    assert r_high["p95_gini"] >= r_low["p95_gini"]
