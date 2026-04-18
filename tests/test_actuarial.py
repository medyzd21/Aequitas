"""Tests for engine.actuarial."""
from __future__ import annotations

import math

from engine import actuarial as act


def test_gompertz_monotone_q():
    g = act.GompertzMakeham()
    qs = [g.q(x) for x in range(20, 100, 5)]
    assert all(0 <= q <= 1 for q in qs)
    assert all(qs[i] <= qs[i + 1] for i in range(len(qs) - 1))


def test_life_table_radix_and_omega():
    t = act.MortalityTable.from_gompertz(radix=100_000.0)
    assert t.l_x(0) == 100_000.0
    assert t.l_x(t.omega + 1) == 0.0
    # strictly non-increasing
    prev = t.l_x(0)
    for x in range(1, t.omega + 1):
        assert t.l_x(x) <= prev
        prev = t.l_x(x)


def test_life_expectancy_reasonable():
    t = act.default_table("U")
    e30 = t.life_expectancy(30)
    e65 = t.life_expectancy(65)
    assert 40 <= e30 <= 65      # plausible
    assert 10 <= e65 <= 30
    assert e30 > e65


def test_annuity_due_positive_and_decreases_with_i():
    t = act.default_table("U")
    a1 = act.annuity_due(t, 30, 0.02)
    a2 = act.annuity_due(t, 30, 0.08)
    assert a1 > a2 > 0


def test_deferred_plus_immediate_equals_whole_life():
    t = act.default_table("U")
    i = 0.04
    x = 40
    n = 5
    whole = act.annuity_due(t, x, i)
    deferred = act.deferred_annuity_due(t, x, n, i)
    # The first n terms of whole-life ä_x, temporary:
    temp = sum((1 / (1 + i)) ** k * t.p(x, k) for k in range(n))
    assert math.isclose(temp + deferred, whole, rel_tol=1e-9)


def test_pure_endowment_bounds():
    t = act.default_table("U")
    nE = act.pure_endowment(t, 30, 30, 0.04)
    assert 0 < nE < 1


def test_annuity_rate_non_negative():
    t = act.default_table("U")
    r = act.annuity_rate(t, 65, 0.04)
    assert r > 0
