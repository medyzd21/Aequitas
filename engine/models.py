"""Core dataclasses for Aequitas.

Keeps the original Member fields (wallet, birth_year, cohort,
total_contributions, piu_balance, active) to stay backward-compatible
with the existing MVP, and adds actuarial fields used by the new modules.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass
class Member:
    """A pension scheme member.

    Backward-compatible with the Phase-1 MVP (wallet, birth_year, cohort,
    total_contributions, piu_balance, active). The rest of the fields drive
    the actuarial projection / valuation modules.
    """
    wallet: str
    birth_year: int
    cohort: int
    # MVP fields
    total_contributions: float = 0.0
    piu_balance: float = 0.0
    active: bool = True
    # Actuarial extension
    salary: float = 40_000.0           # current annual salary
    contribution_rate: float = 0.10    # fraction of salary contributed p.a.
    retirement_age: int = 65           # target retirement age
    sex: str = "U"                     # "M", "F", or "U" (unknown) — used for mortality loading
    join_year: int | None = None       # year member joined the scheme

    def age(self, as_of_year: int) -> int:
        return int(as_of_year) - int(self.birth_year)

    def years_to_retirement(self, as_of_year: int) -> int:
        return max(0, int(self.retirement_age) - self.age(as_of_year))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Proposal:
    """A governance proposal that modifies future benefit streams per cohort.

    `multipliers` maps cohort -> multiplicative change to projected benefits
    (e.g. {1960: 1.03, 1965: 1.00, 1970: 0.97}).
    """
    name: str
    description: str
    multipliers: dict[int, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "multipliers": {int(k): float(v) for k, v in self.multipliers.items()},
        }


@dataclass
class ProjectionRow:
    """One row of a per-member year-by-year projection."""
    year: int
    age: int
    salary: float
    contribution: float
    piu_added: float
    piu_balance: float
    fund_value: float
    benefit_payment: float
    phase: str  # "accumulation", "retired"
    cpi_index: float = 100.0
    piu_price: float = 1.0
    benefit_piu: float = 0.0
    nominal_piu_value: float = 0.0
