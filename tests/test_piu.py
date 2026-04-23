"""Tests for CPI-linked PIU accounting helpers."""
from __future__ import annotations

from engine.piu import (
    PiuIndexRule,
    annual_pension_units_from_balance,
    indexed_epv_from_units,
    indexed_payment_from_units,
    pius_from_contribution,
)
from engine import actuarial as act


def test_piu_price_tracks_cpi_explicitly():
    rule = PiuIndexRule(base_cpi=100.0, base_price=1.0)
    assert rule.price_for_cpi(100.0) == 1.0
    assert rule.price_for_cpi(110.0) == 1.1
    assert rule.cpi_for_price(1.25) == 125.0


def test_higher_price_means_fewer_pius_per_contribution():
    low = pius_from_contribution(1_000.0, 1.0)
    high = pius_from_contribution(1_000.0, 1.25)
    assert low == 1_000.0
    assert high == 800.0
    assert high < low


def test_retirement_converts_piu_balance_into_indexed_pension_flow():
    annual_units = annual_pension_units_from_balance(2_400.0, 20.0)
    payment = indexed_payment_from_units(annual_units, 1.15)
    assert annual_units == 120.0
    assert payment == 138.0


def test_indexed_epv_from_units_is_positive():
    table = act.default_table("F")
    epv = indexed_epv_from_units(
        100.0,
        table,
        65,
        discount_rate=0.03,
        current_piu_price=1.10,
        inflation_rate=0.02,
        defer_years=0,
    )
    assert epv > 0
