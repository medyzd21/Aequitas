"""Synthetic pension population generator.

Produces N plausible `Member` records for the digital-twin simulator.

Design goals
------------
* **Plausibility over realism.** We draw salary, entry age, retirement
  age, sex and contribution rate from distributions a reviewer can sanity
  check by eye. We're not trying to match any one national pension —
  we're trying to give the actuarial engine a population with enough
  variety that intergenerational-fairness stress tests show meaningful
  signal.
* **Deterministic.** Everything is seeded so a scenario rerun produces
  identical members. This is critical for the UI — re-running a scenario
  must give a reproducible event timeline.
* **NumPy-vectorised.** A 100k population generates in < 1 second.
* **No hidden state.** `generate_population(n, seed, cfg)` → list[Member].
  The function is pure given its inputs.

Reused by `engine.system_simulation` but also importable by tests and
by notebooks / scripts that want a starter population.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

import numpy as np

from engine.models import Member


# ---------------------------------------------------------------------------
# PopulationConfig — tunable but with sensible defaults.
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PopulationConfig:
    """Distributions for the synthetic population.

    Parameters
    ----------
    salary_mean / salary_sd : float
        Log-normal salary distribution (in £). salary_sd is in log-space.
    contrib_rate_mean / contrib_rate_sd : float
        Contribution rate ∈ [0.03, 0.15], clipped to a reasonable band.
    age_at_start_min / age_at_start_max : int
        Age of each member at simulation-start year. Uniform in the band.
    retirement_age_choices : tuple[int, ...]
        Retirement ages drawn uniformly from this tuple (65, 67 for UK).
    retirement_age_weights : tuple[float, ...]
        Weights for the choices (must match `retirement_age_choices`).
    female_share : float
        Probability of "F" sex. Mortality loading flows through models.
    wallet_prefix : str
        Short tag used to build human-readable wallets ("0xA_000042").
    """
    salary_mean: float = 40_000.0
    salary_sd: float = 0.35
    contrib_rate_mean: float = 0.085
    contrib_rate_sd: float = 0.015
    age_at_start_min: int = 22
    age_at_start_max: int = 66
    retirement_age_choices: tuple[int, ...] = (65, 67)
    retirement_age_weights: tuple[float, ...] = (0.6, 0.4)
    female_share: float = 0.5
    wallet_prefix: str = "0xS"


# ---------------------------------------------------------------------------
# Core generator
# ---------------------------------------------------------------------------

def generate_population(
    n: int,
    *,
    start_year: int,
    seed: int = 42,
    cfg: PopulationConfig | None = None,
) -> list[Member]:
    """Return `n` plausible members seeded at `start_year`.

    Parameters
    ----------
    n : number of members to generate.
    start_year : simulation start year; used to back-compute birth years
        from the drawn "age at start".
    seed : RNG seed (reproducibility).
    cfg : population configuration; defaults to `PopulationConfig()`.

    The ledger's cohort rule (floor(birth_year / 5) * 5) is applied by
    `CohortLedger.register_member` when these are ingested — we do not
    pre-compute the cohort here.
    """
    cfg = cfg or PopulationConfig()
    if n <= 0:
        return []
    rng = np.random.default_rng(seed)

    # salaries: log-normal around the mean
    salary = rng.lognormal(
        mean=np.log(cfg.salary_mean) - 0.5 * cfg.salary_sd ** 2,
        sigma=cfg.salary_sd,
        size=n,
    )
    # contribution rates: truncated normal, clipped to [0.03, 0.15]
    contrib = np.clip(
        rng.normal(cfg.contrib_rate_mean, cfg.contrib_rate_sd, size=n),
        0.03, 0.15,
    )
    # ages at start
    ages = rng.integers(cfg.age_at_start_min, cfg.age_at_start_max + 1, size=n)
    birth_years = int(start_year) - ages
    # retirement age
    ret_ages = rng.choice(
        list(cfg.retirement_age_choices),
        size=n,
        p=list(cfg.retirement_age_weights),
    )
    # sex
    sex_flip = rng.random(size=n) < cfg.female_share
    sexes = np.where(sex_flip, "F", "M")

    members: list[Member] = []
    for i in range(n):
        wallet = f"{cfg.wallet_prefix}_{i:06d}"
        cohort = (int(birth_years[i]) // 5) * 5
        members.append(
            Member(
                wallet=wallet,
                birth_year=int(birth_years[i]),
                cohort=int(cohort),
                salary=float(round(salary[i], 2)),
                contribution_rate=float(round(contrib[i], 4)),
                retirement_age=int(ret_ages[i]),
                sex=str(sexes[i]),
                join_year=int(start_year),
            )
        )
    return members


# ---------------------------------------------------------------------------
# Entrant stream — used by system_simulation for new-joiner flow
# ---------------------------------------------------------------------------

@dataclass
class EntrantConfig:
    """How many members join per simulated year."""
    mean_per_year: int = 0           # new joiners per year (0 = closed fund)
    entry_age_mean: float = 28.0
    entry_age_sd: float = 4.0
    salary_mean: float = 38_000.0    # starting salary for new joiners
    salary_sd: float = 0.30
    contrib_rate_mean: float = 0.08
    contrib_rate_sd: float = 0.015


def draw_entrants(
    rng: np.random.Generator,
    year: int,
    cfg: EntrantConfig,
    wallet_prefix: str = "0xS",
    wallet_offset: int = 0,
) -> list[Member]:
    """Draw this year's new joiners using the supplied RNG."""
    if cfg.mean_per_year <= 0:
        return []
    # Poisson count of joiners
    n = int(rng.poisson(cfg.mean_per_year))
    if n <= 0:
        return []
    entry_ages = np.clip(
        rng.normal(cfg.entry_age_mean, cfg.entry_age_sd, size=n),
        20, 55,
    ).astype(int)
    salaries = rng.lognormal(
        mean=np.log(cfg.salary_mean) - 0.5 * cfg.salary_sd ** 2,
        sigma=cfg.salary_sd,
        size=n,
    )
    contribs = np.clip(
        rng.normal(cfg.contrib_rate_mean, cfg.contrib_rate_sd, size=n),
        0.03, 0.15,
    )
    ret_ages = rng.choice([65, 67], size=n, p=[0.5, 0.5])
    sex_flip = rng.random(size=n) < 0.5
    sexes = np.where(sex_flip, "F", "M")

    out: list[Member] = []
    for i in range(n):
        wallet = f"{wallet_prefix}_{wallet_offset + i:06d}"
        birth_year = int(year) - int(entry_ages[i])
        cohort = (birth_year // 5) * 5
        out.append(
            Member(
                wallet=wallet,
                birth_year=birth_year,
                cohort=int(cohort),
                salary=float(round(salaries[i], 2)),
                contribution_rate=float(round(contribs[i], 4)),
                retirement_age=int(ret_ages[i]),
                sex=str(sexes[i]),
                join_year=int(year),
            )
        )
    return out


__all__ = [
    "PopulationConfig",
    "EntrantConfig",
    "generate_population",
    "draw_entrants",
]
