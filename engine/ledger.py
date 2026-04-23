"""Cohort-based pension ledger.

The ledger is the single source of truth for member state, contributions, and
Pension Income Units (PIUs). Keeps the original Phase-1 API:

    register_member(wallet, birth_year)
    contribute(wallet, amount)
    get_member_summary(wallet)
    get_all_members()
    cohort_aggregate_contrib

and layers on actuarial valuation helpers used by the new modules.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from engine.models import Member
from engine import actuarial as act
from engine.piu import (
    PiuIndexRule,
    annual_pension_units_from_balance,
    cpi_roll_forward,
    indexed_epv_from_units,
    indexed_payment_from_units,
    nominal_value_of_pius,
    pius_from_contribution,
)


@dataclass
class ValuationSummary:
    wallet: str
    age: int
    epv_contributions: float
    epv_benefits: float
    money_worth_ratio: float
    current_piu_price: float
    current_piu_value: float
    projected_annual_benefit_piu: float
    projected_annual_benefit: float
    replacement_ratio: float


class CohortLedger:
    """Cohort-based ledger of members and contributions.

    piu_price is the nominal NAV of one Pension Income Unit. Every unit of
    currency contributed mints (amount / piu_price) PIUs. In later phases the
    unit price can float with fund performance and the PIU can become a
    tokenised claim.
    """

    # ------------------------------------------------------------------ init
    def __init__(
        self,
        piu_price: float = 1.0,
        valuation_year: int = 2026,
        discount_rate: float = 0.04,
        salary_growth: float = 0.025,
        investment_return: float = 0.05,
        *,
        base_cpi: float = 100.0,
        current_cpi: float | None = None,
        expected_inflation: float = 0.02,
    ):
        self.base_cpi = float(base_cpi)
        self.current_cpi = float(self.base_cpi if current_cpi is None else current_cpi)
        self.expected_inflation = float(expected_inflation)
        self.index_rule = PiuIndexRule(
            base_cpi=self.base_cpi,
            base_price=float(piu_price),
            expected_inflation=self.expected_inflation,
        )
        self.piu_price = self.index_rule.price_for_cpi(self.current_cpi)
        self.valuation_year = valuation_year
        self.discount_rate = discount_rate
        self.salary_growth = salary_growth
        self.investment_return = investment_return

        self.members: dict[str, Member] = {}
        self.cohort_aggregate_contrib: dict[int, float] = {}

    # ----------------------------------------------------------- core MVP API
    def register_member(
        self,
        wallet: str,
        birth_year: int,
        *,
        salary: float = 40_000.0,
        contribution_rate: float = 0.10,
        retirement_age: int = 65,
        sex: str = "U",
    ) -> Member:
        if wallet in self.members:
            raise ValueError("Member already exists")
        cohort = self._cohort_from_birth_year(birth_year)
        member = Member(
            wallet=wallet,
            birth_year=int(birth_year),
            cohort=cohort,
            salary=float(salary),
            contribution_rate=float(contribution_rate),
            retirement_age=int(retirement_age),
            sex=sex.upper(),
            join_year=self.valuation_year,
        )
        self.members[wallet] = member
        self.cohort_aggregate_contrib.setdefault(cohort, 0.0)
        return member

    def contribute(self, wallet: str, amount: float) -> float:
        if wallet not in self.members:
            raise ValueError("Member not registered")
        if amount <= 0:
            raise ValueError("Contribution must be positive")
        m = self.members[wallet]
        piu_accrual = pius_from_contribution(amount, self.piu_price)
        m.total_contributions += amount
        m.piu_balance += piu_accrual
        self.cohort_aggregate_contrib[m.cohort] = (
            self.cohort_aggregate_contrib.get(m.cohort, 0.0) + amount
        )
        return piu_accrual

    def set_cpi_level(self, cpi_level: float) -> float:
        """Set the current CPI level and recompute the live PIU price."""
        self.current_cpi = float(cpi_level)
        self.piu_price = self.index_rule.price_for_cpi(self.current_cpi)
        return self.piu_price

    def apply_cpi_rate(self, inflation_rate: float) -> float:
        """Roll CPI forward by one period and recompute the PIU price."""
        return self.set_cpi_level(cpi_roll_forward(self.current_cpi, inflation_rate))

    def projected_cpi(self, years: int, inflation_rate: float | None = None) -> float:
        return self.index_rule.project_cpi(years, inflation_rate, current_cpi=self.current_cpi)

    def projected_piu_price(self, years: int, inflation_rate: float | None = None) -> float:
        return self.index_rule.project_price(years, inflation_rate, current_cpi=self.current_cpi)

    def piu_nominal_value(self, piu_units: float, price: float | None = None) -> float:
        return nominal_value_of_pius(piu_units, self.piu_price if price is None else price)

    def get_member_summary(self, wallet: str) -> Member:
        if wallet not in self.members:
            raise ValueError("Member not registered")
        return self.members[wallet]

    def get_all_members(self) -> list[Member]:
        return list(self.members.values())

    def _cohort_from_birth_year(self, birth_year: int) -> int:
        return (int(birth_year) // 5) * 5

    # ----------------------------------------------------- actuarial helpers
    def value_member(self, wallet: str) -> ValuationSummary:
        """Compute EPV of future contributions and benefits for one member.

        Future benefit is modelled in PIU units:

        * nominal contributions buy PIUs at the current CPI-linked PIU price,
        * accumulated PIUs convert into an annual pension flow in PIU units,
        * nominal pension payments are those PIU units valued at the future
          PIU price.

        Investment return remains a scheme-funding parameter, but the member's
        promised pension rights are now tracked in PIU space.
        """
        m = self.get_member_summary(wallet)
        x = m.age(self.valuation_year)
        years_to_ret = m.years_to_retirement(self.valuation_year)

        table = act.default_table(m.sex)

        # EPV of future contributions in nominal currency (growing, survival-weighted)
        starting_contrib = m.salary * m.contribution_rate
        epv_c = act.epv_growing_contributions(
            table=table,
            x=x,
            starting_contribution=starting_contrib,
            growth=self.salary_growth,
            years=years_to_ret,
            i=self.discount_rate,
        )

        g = self.salary_growth
        c0 = starting_contrib
        n = years_to_ret
        inflation = self.expected_inflation

        projected_pius = float(m.piu_balance)
        for k in range(max(0, n)):
            contribution_nominal = c0 * ((1.0 + g) ** k)
            projected_price = self.projected_piu_price(k, inflation)
            projected_pius += pius_from_contribution(contribution_nominal, projected_price)

        annuity_factor = act.annuity_due(table, m.retirement_age, self.discount_rate)
        annual_benefit_piu = annual_pension_units_from_balance(projected_pius, annuity_factor)
        price_at_retirement = self.projected_piu_price(n, inflation)
        benefit = indexed_payment_from_units(annual_benefit_piu, price_at_retirement)

        epv_b = indexed_epv_from_units(
            annual_benefit_piu,
            table,
            x,
            discount_rate=self.discount_rate,
            current_piu_price=self.piu_price,
            inflation_rate=inflation,
            defer_years=years_to_ret,
        )

        mwr = 0.0 if epv_c <= 0 else epv_b / epv_c
        final_salary = m.salary * (1.0 + g) ** n
        rr = act.replacement_ratio(benefit, final_salary)

        return ValuationSummary(
            wallet=m.wallet,
            age=x,
            epv_contributions=epv_c,
            epv_benefits=epv_b,
            money_worth_ratio=mwr,
            current_piu_price=self.piu_price,
            current_piu_value=self.piu_nominal_value(m.piu_balance),
            projected_annual_benefit_piu=annual_benefit_piu,
            projected_annual_benefit=benefit,
            replacement_ratio=rr,
        )

    def value_all(self) -> list[ValuationSummary]:
        return [self.value_member(w) for w in self.members]

    def cohort_valuation(self) -> dict[int, dict[str, float]]:
        """Aggregate EPVs by cohort. Returns {cohort: {...}}."""
        out: dict[int, dict[str, float]] = {}
        for s in self.value_all():
            m = self.members[s.wallet]
            row = out.setdefault(
                m.cohort,
                {"epv_contributions": 0.0, "epv_benefits": 0.0, "members": 0},
            )
            row["epv_contributions"] += s.epv_contributions
            row["epv_benefits"] += s.epv_benefits
            row["members"] += 1
        for cohort, row in out.items():
            c = row["epv_contributions"]
            row["money_worth_ratio"] = 0.0 if c <= 0 else row["epv_benefits"] / c
        return out

    # ----------------------------------------------------------- iteration
    def __iter__(self) -> Iterable[Member]:
        return iter(self.members.values())

    def __len__(self) -> int:
        return len(self.members)
