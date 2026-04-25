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
    assert L.active_accumulation_pool_nav == 1_000.0
    assert L.total_active_piu_supply == 1_000.0
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


def test_fund_return_changes_piu_price_and_minting_rate():
    L = CohortLedger(piu_price=1.0, current_cpi=100.0)
    L.register_member("0xB", 1985, salary=60_000)
    base_mint = L.contribute("0xB", 1_000.0)
    assert base_mint == 1_000.0

    L.set_cpi_level(120.0)
    assert L.piu_price == 1.0
    L.apply_investment_return(0.25)
    assert L.raw_piu_price == 1.25
    assert round(L.piu_price, 6) == 1.05
    higher_nav_mint = L.contribute("0xB", 1_000.0)
    assert round(higher_nav_mint, 6) == round(1_000.0 / 1.05, 6)
    assert higher_nav_mint < base_mint


def test_retirement_burns_pius_and_converts_to_annual_benefit():
    L = CohortLedger(piu_price=1.0)
    L.register_member("0xR", 1960, salary=60_000)
    L.contribute("0xR", 10_000.0)
    L.apply_investment_return(0.25)
    pius_burned, capital, annual = L.retire_member("0xR", annuity_factor=20.0)
    assert pius_burned == 10_000.0
    assert capital > 10_000.0
    assert annual == capital / 20.0
    assert L.get_member_summary("0xR").piu_balance == 0.0
    assert L.total_active_piu_supply == 0.0


def test_value_member_reports_piu_fields():
    L = CohortLedger(
        piu_price=1.0,
        current_cpi=108.0,
        expected_inflation=0.02,
        valuation_year=2026,
    )
    L.register_member("0xC", 1982, salary=55_000, contribution_rate=0.11, retirement_age=65)
    L.contribute("0xC", 4_000.0)
    L.apply_investment_return(0.10)
    summary = L.value_member("0xC")
    assert summary.current_piu_price > 1.0
    assert summary.current_piu_value > 0
    assert summary.projected_annual_benefit_piu > 0
