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


@dataclass
class ValuationSummary:
    wallet: str
    age: int
    epv_contributions: float
    epv_benefits: float
    money_worth_ratio: float
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
    ):
        self.piu_price = piu_price
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
        piu_accrual = amount / self.piu_price
        m.total_contributions += amount
        m.piu_balance += piu_accrual
        self.cohort_aggregate_contrib[m.cohort] = (
            self.cohort_aggregate_contrib.get(m.cohort, 0.0) + amount
        )
        return piu_accrual

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

        Future benefit is modelled as: the member continues contributing
        `contribution_rate · salary` (growing at salary_growth) until
        retirement, accumulating at investment_return, then converting into
        a level life annuity using the default mortality table.
        """
        m = self.get_member_summary(wallet)
        x = m.age(self.valuation_year)
        years_to_ret = m.years_to_retirement(self.valuation_year)

        table = act.default_table(m.sex)

        # EPV of future contributions (growing, survival-weighted)
        starting_contrib = m.salary * m.contribution_rate
        epv_c = act.epv_growing_contributions(
            table=table,
            x=x,
            starting_contribution=starting_contrib,
            growth=self.salary_growth,
            years=years_to_ret,
            i=self.discount_rate,
        )

        # Project fund value at retirement from CURRENT PIU balance AND
        # future contributions — deterministic mean.
        r = self.investment_return
        g = self.salary_growth
        c0 = starting_contrib
        n = years_to_ret

        # FV of current fund: piu_balance * piu_price * (1+r)^n
        fv_current = m.piu_balance * self.piu_price * (1.0 + r) ** n

        # FV of growing annuity-due of contributions:
        # Σ_{k=0}^{n-1} c0*(1+g)^k * (1+r)^(n-k)
        if abs(r - g) < 1e-12:
            fv_future_contribs = c0 * (1 + r) * n * (1 + r) ** (n - 1) if n > 0 else 0.0
        else:
            fv_future_contribs = (
                c0 * ((1 + r) ** n - (1 + g) ** n) / (r - g) * (1 + r)
                if n > 0
                else 0.0
            )

        fund_at_retirement = fv_current + fv_future_contribs

        # Convert to annual benefit via annuity rate at retirement age
        benefit = fund_at_retirement * act.annuity_rate(table, m.retirement_age, self.discount_rate)

        # EPV of benefit as deferred annuity at current age
        epv_b = act.epv_deferred_level_benefit(
            table=table,
            x=x,
            benefit=benefit,
            defer_years=years_to_ret,
            i=self.discount_rate,
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
