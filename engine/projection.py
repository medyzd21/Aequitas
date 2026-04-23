"""Year-by-year projections of a member's fund.

Two perspectives are produced:

1.  `project_member` — deterministic path: salary grows at `salary_growth`,
    fund earns `investment_return`. At retirement, fund is converted into
    a level annuity using the default life table; payments continue until
    the mortality table's ω.
2.  `project_fund` — scheme-wide aggregate by year.

All rows include `phase` ∈ {"accumulation", "retired"} so the UI can shade
charts and slice tables.
"""
from __future__ import annotations

import pandas as pd

from engine import actuarial as act
from engine.models import Member, ProjectionRow
from engine.piu import (
    PiuIndexRule,
    annual_pension_units_from_balance,
    cpi_roll_forward,
    indexed_payment_from_units,
    nominal_value_of_pius,
    pius_from_contribution,
)


def project_member(
    member: Member,
    valuation_year: int,
    *,
    salary_growth: float = 0.025,
    investment_return: float = 0.05,
    discount_rate: float = 0.04,
    inflation_rate: float = 0.02,
    horizon: int = 60,
    initial_fund: float | None = None,
    current_cpi: float = 100.0,
    current_piu_price: float = 1.0,
) -> pd.DataFrame:
    """Project one member's salary, contributions, fund, and benefit.

    The projection is now PIU-first:

    * nominal contributions buy PIUs at the current CPI-linked price,
    * retirement converts PIU balances into annual pension PIU units,
    * nominal pension payments are those pension PIU units valued at the
      live PIU price.

    `fund_value` is kept for backward-compatible charts, but now represents
    the nominal value of the accumulated PIU claim (or the remaining nominal
    value of the pension stream once retired), rather than a separate
    investment account.
    """
    table = act.default_table(member.sex)
    x0 = member.age(valuation_year)
    retire_age = int(member.retirement_age)

    salary = float(member.salary)
    piu_balance = float(member.piu_balance if initial_fund is None else initial_fund)
    benefit_piu = 0.0
    cpi_index = float(current_cpi)
    anchor_price = float(current_piu_price) * 100.0 / max(float(current_cpi), 1e-9)
    index_rule = PiuIndexRule(base_cpi=100.0, base_price=anchor_price, expected_inflation=inflation_rate)
    piu_price = index_rule.price_for_cpi(cpi_index)
    rows: list[ProjectionRow] = []

    for k in range(horizon + 1):
        year = valuation_year + k
        age = x0 + k

        if age < retire_age:
            phase = "accumulation"
            contribution = salary * member.contribution_rate
            piu_added = pius_from_contribution(contribution, piu_price)
            piu_balance += piu_added
            benefit_payment = 0.0
            fund = nominal_value_of_pius(piu_balance, piu_price)
            nominal_piu_value = fund
            if age < retire_age - 1:
                salary *= (1.0 + salary_growth)
        else:
            if benefit_piu == 0.0:  # first retirement year — convert PIUs once
                annuity_factor = act.annuity_due(table, retire_age, discount_rate)
                benefit_piu = annual_pension_units_from_balance(piu_balance, annuity_factor)
                piu_balance = 0.0
            contribution = 0.0
            piu_added = 0.0
            phase = "retired"
            benefit_payment = indexed_payment_from_units(benefit_piu, piu_price)
            nominal_piu_value = nominal_value_of_pius(piu_balance, piu_price)
            fund = benefit_payment * act.annuity_due(table, age, discount_rate)

        rows.append(
            ProjectionRow(
                year=year,
                age=age,
                salary=salary if phase == "accumulation" else 0.0,
                contribution=contribution,
                piu_added=piu_added,
                piu_balance=piu_balance if phase == "accumulation" else 0.0,
                fund_value=fund,
                benefit_payment=benefit_payment,
                phase=phase,
                cpi_index=cpi_index,
                piu_price=piu_price,
                benefit_piu=benefit_piu,
                nominal_piu_value=nominal_piu_value,
            )
        )

        # Stop once past plausible max age
        if age >= table.omega:
            break

        cpi_index = cpi_roll_forward(cpi_index, inflation_rate)
        piu_price = index_rule.price_for_cpi(cpi_index)

    return pd.DataFrame([r.__dict__ for r in rows])


def project_fund(
    members: list[Member],
    valuation_year: int,
    *,
    salary_growth: float = 0.025,
    investment_return: float = 0.05,
    discount_rate: float = 0.04,
    inflation_rate: float = 0.02,
    horizon: int = 60,
    current_cpi: float = 100.0,
    current_piu_price: float = 1.0,
) -> pd.DataFrame:
    """Aggregate project_member across a list of members.

    Returns a DataFrame indexed by year with columns: contributions,
    benefit_payments, fund_value, active_contributors, retirees.
    """
    if not members:
        return pd.DataFrame(
            columns=[
                "year",
                "contributions",
                "benefit_payments",
                "fund_value",
                "total_pius",
                "cpi_index",
                "piu_price",
                "active_contributors",
                "retirees",
            ]
        )

    frames = []
    for m in members:
        df = project_member(
            m,
            valuation_year,
            salary_growth=salary_growth,
            investment_return=investment_return,
            discount_rate=discount_rate,
            inflation_rate=inflation_rate,
            horizon=horizon,
            current_cpi=current_cpi,
            current_piu_price=current_piu_price,
        )
        df["wallet"] = m.wallet
        frames.append(df)
    combined = pd.concat(frames, ignore_index=True)

    grouped = (
        combined.groupby("year")
        .agg(
            contributions=("contribution", "sum"),
            benefit_payments=("benefit_payment", "sum"),
            fund_value=("fund_value", "sum"),
            total_pius=("piu_balance", "sum"),
            cpi_index=("cpi_index", "mean"),
            piu_price=("piu_price", "mean"),
            active_contributors=("phase", lambda s: (s == "accumulation").sum()),
            retirees=("phase", lambda s: (s == "retired").sum()),
        )
        .reset_index()
    )
    return grouped
