"""Tests for engine.ledger."""
from __future__ import annotations

import pytest

from engine.ledger import CohortLedger


def test_register_and_contribute():
    L = CohortLedger(piu_price=1.0)
    L.register_member("0xA", 1970, salary=50_000)
    piu = L.contribute("0xA", 1_000.0)
    assert piu == 1_000.0
    m = L.get_member_summary("0xA")
    assert m.total_contributions == 1_000.0
    assert m.piu_balance == 1_000.0
    # cohort bucket updated
    assert L.cohort_aggregate_contrib[1970] == 1_000.0


def test_duplicate_member_fails():
    L = CohortLedger()
    L.register_member("w", 1980)
    with pytest.raises(ValueError):
        L.register_member("w", 1980)


def test_contribute_unknown_member_fails():
    L = CohortLedger()
    with pytest.raises(ValueError):
        L.contribute("nobody", 100.0)


def test_cohort_bucketing():
    L = CohortLedger()
    L.register_member("a", 1969)   # cohort 1965
    L.register_member("b", 1970)   # cohort 1970
    assert L.get_member_summary("a").cohort == 1965
    assert L.get_member_summary("b").cohort == 1970


def test_value_member_basic():
    L = CohortLedger(valuation_year=2026, discount_rate=0.04,
                      salary_growth=0.025, investment_return=0.05)
    L.register_member("x", 1980, salary=50_000, contribution_rate=0.10,
                       retirement_age=65)
    L.contribute("x", 5_000)
    s = L.value_member("x")
    assert s.epv_contributions > 0
    assert s.epv_benefits > 0
    assert 0 < s.money_worth_ratio < 5
    assert 0 < s.replacement_ratio < 2
