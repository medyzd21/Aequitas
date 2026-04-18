"""Monte Carlo simulation of pension outcomes.

We model investment returns as i.i.d. log-normal with mean `mu` and
volatility `sigma`. Contributions are paid in advance each year, conditional
on survival; at retirement the fund converts to an annuity using the default
mortality table.

The module returns a DataFrame of per-path terminal values and a percentile
summary convenient for the Streamlit UI.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from engine import actuarial as act
from engine.models import Member


def simulate_member(
    member: Member,
    valuation_year: int,
    *,
    n_paths: int = 2_000,
    mu: float = 0.05,
    sigma: float = 0.10,
    salary_growth: float = 0.025,
    discount_rate: float = 0.04,
    seed: int | None = 42,
) -> dict:
    """Monte-Carlo a single member's retirement fund and annual benefit.

    Returns:
        {
          "paths": DataFrame  (one row per path, columns: fund_at_ret,
                                benefit, replacement_ratio),
          "percentiles": DataFrame with p5/p25/p50/p75/p95 for each column,
          "time_series": DataFrame of year-by-year percentiles of fund value,
        }
    """
    rng = np.random.default_rng(seed)
    table = act.default_table(member.sex)
    x0 = member.age(valuation_year)
    retire_age = int(member.retirement_age)
    n = max(0, retire_age - x0)

    # Log-normal shocks
    # returns_{k} ~ LogNormal(mean=mu, sigma=sigma). We interpret mu as
    # arithmetic mean per-period return.
    m = mu
    s = sigma
    log_mu = np.log((1 + m) ** 2 / np.sqrt((1 + m) ** 2 + s ** 2))
    log_sd = np.sqrt(np.log(1 + s ** 2 / (1 + m) ** 2))
    shocks = rng.lognormal(mean=log_mu, sigma=log_sd, size=(n_paths, max(1, n)))

    # Accumulate
    fund0 = float(member.piu_balance)  # treat PIU price = 1.0 here
    salary = float(member.salary)
    contrib_rate = float(member.contribution_rate)

    fund_matrix = np.zeros((n_paths, n + 1))
    fund_matrix[:, 0] = fund0
    sal = salary
    for k in range(n):
        contribution = sal * contrib_rate
        fund_matrix[:, k + 1] = (fund_matrix[:, k] + contribution) * shocks[:, k]
        sal *= (1 + salary_growth)

    terminal = fund_matrix[:, -1]
    annuity_rate = act.annuity_rate(table, retire_age, discount_rate)
    benefit = terminal * annuity_rate
    final_salary = salary  # salary after n growth steps
    rr = benefit / final_salary if final_salary > 0 else np.zeros_like(benefit)

    paths = pd.DataFrame(
        {
            "fund_at_retirement": terminal,
            "annual_benefit": benefit,
            "replacement_ratio": rr,
        }
    )

    qs = [0.05, 0.25, 0.5, 0.75, 0.95]
    pct = paths.quantile(qs).rename(index=lambda q: f"p{int(q*100):02d}")

    # Time series of fund-value percentiles
    years = np.arange(valuation_year, valuation_year + n + 1)
    ts_pct = pd.DataFrame(
        np.quantile(fund_matrix, qs, axis=0).T,
        columns=[f"p{int(q*100):02d}" for q in qs],
    )
    ts_pct.insert(0, "year", years)

    return {"paths": paths, "percentiles": pct, "time_series": ts_pct}


def simulate_fund(
    members: list[Member],
    valuation_year: int,
    *,
    n_paths: int = 500,
    mu: float = 0.05,
    sigma: float = 0.10,
    salary_growth: float = 0.025,
    discount_rate: float = 0.04,
    seed: int | None = 42,
) -> pd.DataFrame:
    """Scheme-level percentiles of aggregate fund value.

    Keeps `n_paths` modest — this sums member-level simulations with a shared
    return seed per year so cross-sectional correlations are preserved.
    """
    rng = np.random.default_rng(seed)
    if not members:
        return pd.DataFrame(columns=["year", "p05", "p25", "p50", "p75", "p95"])

    max_n = max(max(0, m.retirement_age - m.age(valuation_year)) for m in members)
    # Shared shocks — one per path per year, so every member sees the same
    # market return in the same scenario.
    m_ret = 0.05 if mu is None else mu
    log_mu = np.log((1 + m_ret) ** 2 / np.sqrt((1 + m_ret) ** 2 + sigma ** 2))
    log_sd = np.sqrt(np.log(1 + sigma ** 2 / (1 + m_ret) ** 2))
    shocks = rng.lognormal(mean=log_mu, sigma=log_sd, size=(n_paths, max(1, max_n)))

    agg = np.zeros((n_paths, max_n + 1))
    for member in members:
        x0 = member.age(valuation_year)
        n = max(0, int(member.retirement_age) - x0)
        sal = float(member.salary)
        fund0 = float(member.piu_balance)
        fund = np.full(n_paths, fund0)
        agg[:, 0] += fund
        for k in range(n):
            fund = (fund + sal * member.contribution_rate) * shocks[:, k]
            sal *= (1 + salary_growth)
            if k + 1 <= max_n:
                agg[:, k + 1] += fund

    qs = [0.05, 0.25, 0.5, 0.75, 0.95]
    out = pd.DataFrame(
        np.quantile(agg, qs, axis=0).T,
        columns=[f"p{int(q*100):02d}" for q in qs],
    )
    out.insert(0, "year", np.arange(valuation_year, valuation_year + max_n + 1))
    return out
