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


def project_member(
    member: Member,
    valuation_year: int,
    *,
    salary_growth: float = 0.025,
    investment_return: float = 0.05,
    discount_rate: float = 0.04,
    horizon: int = 60,
    initial_fund: float | None = None,
) -> pd.DataFrame:
    """Project one member's salary, contributions, fund, and benefit.

    `initial_fund` defaults to (piu_balance · 1.0) — we treat PIU price = 1.0
    for projections; the ledger keeps the real PIU price separately.
    """
    table = act.default_table(member.sex)
    x0 = member.age(valuation_year)
    retire_age = int(member.retirement_age)

    salary = float(member.salary)
    fund = float(member.piu_balance if initial_fund is None else initial_fund)

    # One-off annuity conversion at retirement
    annuity_rate = act.annuity_rate(table, retire_age, discount_rate)
    benefit = 0.0
    rows: list[ProjectionRow] = []

    for k in range(horizon + 1):
        year = valuation_year + k
        age = x0 + k

        if age < retire_age:
            phase = "accumulation"
            contribution = salary * member.contribution_rate
            piu_added = contribution  # PIU price = 1.0 in projection-space
            # interest on beginning fund, contribution paid in advance
            fund = (fund + contribution) * (1.0 + investment_return)
            benefit_payment = 0.0
            if age < retire_age - 1:
                salary *= (1.0 + salary_growth)
        else:
            if benefit == 0.0:  # first retirement year — convert fund once
                benefit = fund * annuity_rate
                contribution = 0.0
                piu_added = 0.0
            else:
                contribution = 0.0
                piu_added = 0.0
            phase = "retired"
            benefit_payment = benefit
            fund = max(0.0, (fund - benefit_payment) * (1.0 + investment_return))

        rows.append(
            ProjectionRow(
                year=year,
                age=age,
                salary=salary if phase == "accumulation" else 0.0,
                contribution=contribution,
                piu_added=piu_added,
                piu_balance=fund / 1.0,  # 1:1 mapping in projection space
                fund_value=fund,
                benefit_payment=benefit_payment,
                phase=phase,
            )
        )

        # Stop once past plausible max age
        if age >= table.omega:
            break

    return pd.DataFrame([r.__dict__ for r in rows])


def project_fund(
    members: list[Member],
    valuation_year: int,
    *,
    salary_growth: float = 0.025,
    investment_return: float = 0.05,
    discount_rate: float = 0.04,
    horizon: int = 60,
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
            horizon=horizon,
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
            active_contributors=("phase", lambda s: (s == "accumulation").sum()),
            retirees=("phase", lambda s: (s == "retired").sum()),
        )
        .reset_index()
    )
    return grouped
