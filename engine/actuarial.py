"""Actuarial core: mortality, annuity factors, and expected present values.

Implements a transparent Gompertz–Makeham mortality model and classical life
annuity / deferred annuity factors so a Master's reviewer can trace every
number back to its formula. The defaults give ≈ 80-year life expectancy at
age 30 — realistic enough for demo use without needing licensed tables.

Notation (standard actuarial):
    μ_x     force of mortality at age x
    q_x     one-year probability of death at age x
    p_x     = 1 − q_x
    l_x     survivors to age x from a radix
    v       = 1 / (1 + i)   annual discount factor
    ä_x     annuity-due, whole-life, paid annually
    n|ä_x   n-year deferred annuity-due

All functions are pure (no global state). Pass an explicit MortalityTable.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import math


# ---------------------------------------------------------------------------
# Mortality
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class GompertzMakeham:
    """Gompertz–Makeham force of mortality: μ_x = A + B · c^x.

    Default parameters loosely calibrated so e_30 ≈ 50 years (total ≈ 80).
    A small sex-loading can be applied via `sex_loading` at build time.
    """
    # Defaults calibrated so e_0 ≈ 79, e_30 ≈ 50, e_65 ≈ 19 — close to
    # modern mixed-population UK / US statistics.
    A: float = 0.0002     # age-independent (accidents etc.)
    B: float = 3.5e-5     # Gompertz baseline
    c: float = 1.095      # age-acceleration
    omega: int = 115      # ultimate age (force survival = 0 past this)

    def mu(self, x: float) -> float:
        return self.A + self.B * (self.c ** x)

    def q(self, x: int) -> float:
        """One-year probability of death at integer age x."""
        if x >= self.omega:
            return 1.0
        # q_x ≈ 1 − exp(−∫ μ) with piecewise-constant μ over the year.
        return 1.0 - math.exp(-self.mu(x + 0.5))


@dataclass
class MortalityTable:
    """Concrete life table: l_x for every integer age 0..omega."""
    l: list[float]  # l[x] = survivors to age x from radix l[0]
    omega: int

    @classmethod
    def from_gompertz(
        cls,
        model: GompertzMakeham | None = None,
        radix: float = 100_000.0,
        sex_loading: float = 1.0,
    ) -> "MortalityTable":
        """Build a life table from a Gompertz–Makeham model.

        `sex_loading` multiplies the force of mortality — use values > 1.0
        for male lives (shorter life expectancy), < 1.0 for female lives.
        """
        model = model or GompertzMakeham()
        omega = model.omega
        l = [0.0] * (omega + 1)
        l[0] = radix
        for x in range(omega):
            q = min(1.0, sex_loading * model.q(x))
            l[x + 1] = l[x] * (1.0 - q)
        return cls(l=l, omega=omega)

    # ----- basic survival ---------------------------------------------------

    def l_x(self, x: int) -> float:
        if x < 0:
            return self.l[0]
        if x > self.omega:
            return 0.0
        return self.l[x]

    def p(self, x: int, n: int = 1) -> float:
        """n-year survival probability  n p_x = l_(x+n) / l_x."""
        lx = self.l_x(x)
        if lx <= 0:
            return 0.0
        return self.l_x(x + n) / lx

    def q(self, x: int, n: int = 1) -> float:
        """n-year death probability  n q_x = 1 − n p_x."""
        return 1.0 - self.p(x, n)

    # ----- expectancy -------------------------------------------------------

    def life_expectancy(self, x: int) -> float:
        """Curtate life expectancy e_x = Σ_{k≥1} k p_x."""
        if x >= self.omega:
            return 0.0
        total = 0.0
        lx = self.l_x(x)
        if lx <= 0:
            return 0.0
        for age in range(x + 1, self.omega + 1):
            total += self.l_x(age) / lx
        return total


# ---------------------------------------------------------------------------
# Annuity factors & present values
# ---------------------------------------------------------------------------

def discount_factor(i: float) -> float:
    """Annual discount factor v = 1 / (1 + i)."""
    return 1.0 / (1.0 + i)


def annuity_due(table: MortalityTable, x: int, i: float, term: int | None = None) -> float:
    """Annuity-due ä_x (or ä_{x:n|} if term given).

    ä_x = Σ_{k=0}^{∞} v^k · k p_x
    First payment at age x (time 0), then yearly while alive.
    """
    v = discount_factor(i)
    if term is None:
        term = table.omega - x + 1
    term = max(0, min(term, table.omega - x + 1))
    total = 0.0
    for k in range(term):
        total += (v ** k) * table.p(x, k)
    return total


def deferred_annuity_due(table: MortalityTable, x: int, n: int, i: float) -> float:
    """n-year deferred whole-life annuity-due  n|ä_x.

    = Σ_{k=n}^{∞} v^k · k p_x
    Payments begin at age x+n if alive.
    """
    if n < 0:
        n = 0
    v = discount_factor(i)
    total = 0.0
    for k in range(n, table.omega - x + 1):
        total += (v ** k) * table.p(x, k)
    return total


def pure_endowment(table: MortalityTable, x: int, n: int, i: float) -> float:
    """n-year pure endowment  nE_x = v^n · n p_x."""
    v = discount_factor(i)
    return (v ** n) * table.p(x, n)


# ---------------------------------------------------------------------------
# EPVs — contributions & benefits
# ---------------------------------------------------------------------------

def epv_level_contributions(
    table: MortalityTable,
    x: int,
    contribution: float,
    years: int,
    i: float,
) -> float:
    """EPV of a level contribution stream of `contribution` paid in advance
    each year for `years` years while alive, at interest `i`."""
    return contribution * annuity_due(table, x, i, term=years)


def epv_growing_contributions(
    table: MortalityTable,
    x: int,
    starting_contribution: float,
    growth: float,
    years: int,
    i: float,
) -> float:
    """EPV of contributions that grow at rate `growth` per year (e.g. salary
    growth × contribution rate). Paid in advance, conditional on survival."""
    v = discount_factor(i)
    total = 0.0
    c = starting_contribution
    for k in range(max(0, years)):
        total += c * (v ** k) * table.p(x, k)
        c *= (1.0 + growth)
    return total


def epv_deferred_level_benefit(
    table: MortalityTable,
    x: int,
    benefit: float,
    defer_years: int,
    i: float,
) -> float:
    """EPV at age x of a level whole-life benefit of `benefit` per year
    starting at age x + defer_years. Equal to benefit · defer_years|ä_x."""
    return benefit * deferred_annuity_due(table, x, defer_years, i)


# ---------------------------------------------------------------------------
# Replacement-ratio helper
# ---------------------------------------------------------------------------

def annuity_rate(table: MortalityTable, x: int, i: float) -> float:
    """Annual annuity payout per 1 unit of capital at age x (immediate life
    annuity-due). capital = ä_x · payment  ⇒  payment = capital / ä_x."""
    a = annuity_due(table, x, i)
    return 0.0 if a <= 0 else 1.0 / a


def replacement_ratio(
    annual_benefit: float,
    final_salary: float,
) -> float:
    return 0.0 if final_salary <= 0 else annual_benefit / final_salary


# ---------------------------------------------------------------------------
# Convenience — default table used across the app
# ---------------------------------------------------------------------------

def default_table(sex: str = "U") -> MortalityTable:
    """Return a cached default table. Male lives get a +15% loading, female
    lives −12% (rough differentiation — for demo only)."""
    loading = {"M": 1.15, "F": 0.88, "U": 1.0}.get(sex.upper(), 1.0)
    return MortalityTable.from_gompertz(sex_loading=loading)
