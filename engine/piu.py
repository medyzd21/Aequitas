"""PIU economics — CPI-linked pension unit accounting helpers.

PIU is Aequitas' pension unit of account:

* Contributions buy PIUs at the current nominal PIU price.
* The PIU price is linked to CPI by an explicit indexing rule.
* Retirement converts accumulated PIUs into an annual pension flow in PIU
  units, not in fixed nominal currency.
* Nominal benefits are the pension PIU flow multiplied by the current PIU
  price, so inflation shows up transparently in benefit pressure.

The Solidity layer stores the live PIU price via `CohortLedger.setPiuPrice`.
The Python engine remains the source of truth for *why* that price moved.
"""
from __future__ import annotations

from dataclasses import dataclass


MIN_PRICE = 1e-9


@dataclass(frozen=True)
class PiuIndexRule:
    """Explicit CPI-to-PIU rule used by the engine.

    `base_cpi` and `base_price` define the anchor point:

        piu_price_t = base_price * cpi_t / base_cpi

    This is intentionally simple and inspectable. If the protocol later wants
    smoothing or caps, they can be layered on top of this rule without
    changing the unit-accounting primitives.
    """

    base_cpi: float = 100.0
    base_price: float = 1.0
    expected_inflation: float = 0.02

    def price_for_cpi(self, cpi_level: float) -> float:
        cpi = max(float(cpi_level), 1e-9)
        return max(MIN_PRICE, float(self.base_price) * cpi / max(float(self.base_cpi), 1e-9))

    def cpi_for_price(self, piu_price: float) -> float:
        price = max(float(piu_price), MIN_PRICE)
        return max(1e-9, float(self.base_cpi) * price / max(float(self.base_price), MIN_PRICE))

    def project_cpi(self, years: int, inflation_rate: float | None = None, *, current_cpi: float | None = None) -> float:
        infl = float(self.expected_inflation if inflation_rate is None else inflation_rate)
        cpi0 = float(self.base_cpi if current_cpi is None else current_cpi)
        return max(1e-9, cpi0 * ((1.0 + infl) ** max(int(years), 0)))

    def project_price(self, years: int, inflation_rate: float | None = None, *, current_cpi: float | None = None) -> float:
        return self.price_for_cpi(self.project_cpi(years, inflation_rate, current_cpi=current_cpi))


def cpi_roll_forward(current_cpi: float, inflation_rate: float) -> float:
    """Advance the CPI level by one period."""
    return max(1e-9, float(current_cpi) * (1.0 + float(inflation_rate)))


def pius_from_contribution(nominal_amount: float, piu_price: float) -> float:
    """How many PIUs a nominal contribution buys at the current price."""
    if float(nominal_amount) <= 0:
        raise ValueError("nominal contribution must be positive")
    return float(nominal_amount) / max(float(piu_price), MIN_PRICE)


def nominal_value_of_pius(piu_units: float, piu_price: float) -> float:
    """Translate PIU units back into nominal currency at the current price."""
    return float(piu_units) * max(float(piu_price), MIN_PRICE)


def annual_pension_units_from_balance(piu_balance: float, annuity_factor: float) -> float:
    """Convert an accumulated PIU balance into annual pension PIU units."""
    factor = max(float(annuity_factor), MIN_PRICE)
    return max(0.0, float(piu_balance)) / factor


def indexed_payment_from_units(annual_pension_units: float, piu_price: float) -> float:
    """Nominal annual pension implied by pension PIU units."""
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
    """EPV of a pension flow that is fixed in PIU units but nominally CPI-linked.

    Payment at time k is:

        annual_pension_units * current_piu_price * (1 + inflation_rate)^k

    for k >= defer_years while the member survives.
    """
    units = max(0.0, float(annual_pension_units))
    if units <= 0:
        return 0.0
    v = 1.0 / (1.0 + float(discount_rate))
    infl = 1.0 + float(inflation_rate)
    total = 0.0
    for k in range(max(int(defer_years), 0), table.omega - int(x) + 1):
        total += units * float(current_piu_price) * (infl ** k) * (v ** k) * table.p(int(x), k)
    return total


__all__ = [
    "MIN_PRICE",
    "PiuIndexRule",
    "annual_pension_units_from_balance",
    "cpi_roll_forward",
    "indexed_epv_from_units",
    "indexed_payment_from_units",
    "nominal_value_of_pius",
    "pius_from_contribution",
]
