"""Tests for fund-linked PIU accounting helpers."""
from __future__ import annotations

from engine.piu import (
    annual_pension_from_capital,
    annual_pension_units_from_balance,
    indexed_epv_from_units,
    indexed_payment_from_units,
    pius_from_contribution,
    raw_piu_price,
    smooth_piu_price,
    update_piu_price,
)
from engine import actuarial as act


def test_raw_piu_price_tracks_nav_per_active_supply():
    assert raw_piu_price(1_200.0, 1_000.0) == 1.2
    assert raw_piu_price(0.0, 0.0, initial_price=1.0) == 1.0


def test_smoothing_formula_blends_previous_and_raw_price():
    assert smooth_piu_price(1.0, 1.5, 0.8) == 1.1
    state = update_piu_price(1_500.0, 1_000.0, 1.0, 0.8)
    assert state.raw_piu_price == 1.5
    assert state.published_piu_price == 1.1


def test_higher_price_means_fewer_pius_per_contribution():
    low = pius_from_contribution(1_000.0, 1.0)
    high = pius_from_contribution(1_000.0, 1.25)
    assert low == 1_000.0
    assert high == 800.0
    assert high < low


def test_retirement_converts_piu_balance_into_actuarial_pension_flow():
    annual_units = annual_pension_units_from_balance(2_400.0, 20.0, 1.15)
    payment = indexed_payment_from_units(annual_units, 1.0)
    assert annual_pension_from_capital(2_760.0, 20.0) == 138.0
    assert annual_units == 138.0
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
