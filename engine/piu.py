"""PIU economics — fund-linked pension accumulation units.

PIUs are non-transferable pension fund units. Members receive PIUs when they
contribute. The published PIU price is a smoothed view of the active
accumulation pool's NAV per active PIU. At retirement, accumulated PIUs are
consumed and converted into a pension stream by the actuarial annuity factor.

The chain records the published price and commitments to NAV/supply/result
bundles. Python remains the source of truth for full fund valuation and
actuarial conversion.
"""
from __future__ import annotations

from dataclasses import dataclass


MIN_PRICE = 1e-9
DEFAULT_INITIAL_PRICE = 1.0
DEFAULT_SMOOTHING_WEIGHT = 0.8


@dataclass(frozen=True)
class PiuPriceState:
    """Serializable snapshot of the PIU price policy."""

    active_accumulation_pool_nav: float
    total_active_piu_supply: float
    raw_piu_price: float
    previous_published_piu_price: float
    smoothing_weight: float
    published_piu_price: float


def validate_smoothing_weight(smoothing_weight: float) -> float:
    weight = float(smoothing_weight)
    if not 0.0 <= weight <= 1.0:
        raise ValueError("smoothing_weight must be between 0 and 1")
    return weight


def raw_piu_price(active_accumulation_pool_nav: float, total_active_piu_supply: float, *, initial_price: float = DEFAULT_INITIAL_PRICE) -> float:
    """NAV-per-active-PIU before smoothing."""
    nav = float(active_accumulation_pool_nav)
    supply = float(total_active_piu_supply)
    if nav < 0:
        raise ValueError("active_accumulation_pool_nav cannot be negative")
    if supply <= 0:
        return max(MIN_PRICE, float(initial_price))
    return max(MIN_PRICE, nav / supply)


def smooth_piu_price(previous_published_piu_price: float, raw_price: float, smoothing_weight: float = DEFAULT_SMOOTHING_WEIGHT) -> float:
    """Published price = w * previous + (1-w) * raw NAV price."""
    weight = validate_smoothing_weight(smoothing_weight)
    previous = max(MIN_PRICE, float(previous_published_piu_price))
    raw = max(MIN_PRICE, float(raw_price))
    return max(MIN_PRICE, weight * previous + (1.0 - weight) * raw)


def update_piu_price(
    active_accumulation_pool_nav: float,
    total_active_piu_supply: float,
    previous_published_piu_price: float,
    smoothing_weight: float = DEFAULT_SMOOTHING_WEIGHT,
    *,
    initial_price: float = DEFAULT_INITIAL_PRICE,
) -> PiuPriceState:
    raw = raw_piu_price(active_accumulation_pool_nav, total_active_piu_supply, initial_price=initial_price)
    published = smooth_piu_price(previous_published_piu_price, raw, smoothing_weight)
    return PiuPriceState(
        active_accumulation_pool_nav=float(active_accumulation_pool_nav),
        total_active_piu_supply=float(total_active_piu_supply),
        raw_piu_price=raw,
        previous_published_piu_price=max(MIN_PRICE, float(previous_published_piu_price)),
        smoothing_weight=float(smoothing_weight),
        published_piu_price=published,
    )


def cpi_roll_forward(current_cpi: float, inflation_rate: float) -> float:
    """Advance CPI as a macro/inflation variable, not as the PIU price driver."""
    return max(1e-9, float(current_cpi) * (1.0 + float(inflation_rate)))


def pius_from_contribution(nominal_amount: float, piu_price: float) -> float:
    """How many non-transferable PIUs a nominal contribution buys."""
    if float(nominal_amount) <= 0:
        raise ValueError("nominal contribution must be positive")
    return float(nominal_amount) / max(float(piu_price), MIN_PRICE)


def nominal_value_of_pius(piu_units: float, piu_price: float) -> float:
    """Translate PIU units into accumulation capital at the published price."""
    return max(0.0, float(piu_units)) * max(float(piu_price), MIN_PRICE)


def annual_pension_from_capital(retirement_capital: float, annuity_factor: float) -> float:
    """Actuarial retirement conversion: capital / annuity factor."""
    factor = max(float(annuity_factor), MIN_PRICE)
    return max(0.0, float(retirement_capital)) / factor


def annual_pension_units_from_balance(piu_balance: float, annuity_factor: float, piu_price: float = 1.0) -> float:
    """Backward-compatible helper returning annual currency benefit.

    Older code called this "pension units"; under the corrected model the
    economic output is annual pension currency from PIU capital.
    """
    return annual_pension_from_capital(nominal_value_of_pius(piu_balance, piu_price), annuity_factor)


def indexed_payment_from_units(annual_pension_units: float, piu_price: float) -> float:
    """Compatibility wrapper for older projections.

    Benefit indexation is no longer driven by PIU price; callers that already
    pass an annual currency benefit should use piu_price=1.
    """
    return max(0.0, float(annual_pension_units)) * max(float(piu_price), MIN_PRICE)


def indexed_epv_from_units(
    annual_pension_units: float,
    table,
    x: int,
    *,
    discount_rate: float,
    current_piu_price: float,
    inflation_rate: float,
    defer_years: int = 0,
) -> float:
    """EPV of an annual pension amount with CPI-like benefit escalation.

    CPI can still affect benefit pressure, but it is no longer the primary
    PIU price driver.
    """
    annual = max(0.0, float(annual_pension_units)) * max(float(current_piu_price), MIN_PRICE)
    if annual <= 0:
        return 0.0
    v = 1.0 / (1.0 + float(discount_rate))
    infl = 1.0 + float(inflation_rate)
    total = 0.0
    for k in range(max(int(defer_years), 0), table.omega - int(x) + 1):
        total += annual * (infl ** k) * (v ** k) * table.p(int(x), k)
    return total


__all__ = [
    "DEFAULT_INITIAL_PRICE",
    "DEFAULT_SMOOTHING_WEIGHT",
    "MIN_PRICE",
    "PiuPriceState",
    "annual_pension_from_capital",
    "annual_pension_units_from_balance",
    "cpi_roll_forward",
    "indexed_epv_from_units",
    "indexed_payment_from_units",
    "nominal_value_of_pius",
    "pius_from_contribution",
    "raw_piu_price",
    "smooth_piu_price",
    "update_piu_price",
    "validate_smoothing_weight",
]
