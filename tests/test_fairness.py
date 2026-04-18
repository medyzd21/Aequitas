"""Tests for engine.fairness."""
from __future__ import annotations

import math

from engine.fairness import (
    evaluate_proposal,
    fairness_corridor_check,
    intergenerational_index,
    mwr_dispersion,
    mwr_gini,
)


def test_corridor_passes_uniform_change():
    old = {1: 100.0, 2: 100.0, 3: 100.0}
    new = {1: 102.0, 2: 102.0, 3: 102.0}
    r = fairness_corridor_check(old, new, epv_benchmark=100.0, delta=0.05)
    assert r["passes"] is True
    assert r["max_deviation"] == 0.0


def test_corridor_fails_asymmetric_change():
    old = {1: 100.0, 2: 100.0, 3: 100.0}
    new = {1: 110.0, 2: 100.0, 3: 82.0}   # big spread
    r = fairness_corridor_check(old, new, epv_benchmark=100.0, delta=0.05)
    assert r["passes"] is False
    assert r["max_deviation"] > 0.05


def test_dispersion_sanity():
    d = mwr_dispersion({1: 1.0, 2: 1.2, 3: 0.8})
    assert math.isclose(d["mean"], 1.0, abs_tol=1e-9)
    assert math.isclose(d["range"], 0.4, abs_tol=1e-9)


def test_gini_zero_when_equal():
    assert mwr_gini({1: 1.0, 2: 1.0, 3: 1.0}) == 0.0


def test_gini_positive_when_unequal():
    assert mwr_gini({1: 0.5, 2: 1.0, 3: 2.0}) > 0.0


def test_intergen_index_bounds():
    assert intergenerational_index({1: 1.0}) == 1.0
    assert 0.0 <= intergenerational_index({1: 0.5, 2: 1.5}) <= 1.0


def test_evaluate_proposal():
    cv = {
        1960: {"epv_contributions": 100.0, "epv_benefits": 110.0,
               "money_worth_ratio": 1.1, "members": 2},
        1970: {"epv_contributions": 100.0, "epv_benefits": 100.0,
               "money_worth_ratio": 1.0, "members": 3},
        1980: {"epv_contributions": 100.0, "epv_benefits": 90.0,
               "money_worth_ratio": 0.9, "members": 4},
    }
    # balanced — mild scaling
    r = evaluate_proposal(cv, {1960: 1.01, 1970: 1.01, 1980: 1.01}, delta=0.05)
    assert r["passes"] is True
    # unfair — divergent
    r2 = evaluate_proposal(cv, {1960: 1.15, 1970: 1.0, 1980: 0.85}, delta=0.05)
    assert r2["passes"] is False
