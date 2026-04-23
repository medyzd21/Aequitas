"""Vectorized synthetic population builder for Digital Twin V2.

The V2 twin keeps heterogeneity at the person level, but stores it in
NumPy arrays instead of Python objects so 100k-member runs remain fast.
The UI only renders aggregate histories plus a handful of representative
stories; the full person arrays stay inside the simulator.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


STATUS_ACTIVE = 0
STATUS_RETIRED = 1
STATUS_DECEASED = 2

SEX_MALE = 0
SEX_FEMALE = 1


@dataclass(frozen=True)
class PopulationStyle:
    """High-level shape of the synthetic society."""

    key: str
    age_weights: tuple[float, float, float, float]
    salary_anchor: float
    entrant_salary_anchor: float
    entrant_rate: float
    contribution_mean: float
    reserve_capture: float


POPULATION_STYLES: dict[str, PopulationStyle] = {
    "balanced": PopulationStyle(
        key="balanced",
        age_weights=(0.28, 0.32, 0.22, 0.18),
        salary_anchor=46_000.0,
        entrant_salary_anchor=34_000.0,
        entrant_rate=0.020,
        contribution_mean=0.092,
        reserve_capture=0.05,
    ),
    "growth": PopulationStyle(
        key="growth",
        age_weights=(0.38, 0.33, 0.18, 0.11),
        salary_anchor=50_000.0,
        entrant_salary_anchor=37_000.0,
        entrant_rate=0.026,
        contribution_mean=0.090,
        reserve_capture=0.04,
    ),
    "mature": PopulationStyle(
        key="mature",
        age_weights=(0.17, 0.26, 0.28, 0.29),
        salary_anchor=44_000.0,
        entrant_salary_anchor=31_000.0,
        entrant_rate=0.012,
        contribution_mean=0.097,
        reserve_capture=0.07,
    ),
    "fragile": PopulationStyle(
        key="fragile",
        age_weights=(0.23, 0.29, 0.25, 0.23),
        salary_anchor=40_000.0,
        entrant_salary_anchor=29_000.0,
        entrant_rate=0.016,
        contribution_mean=0.085,
        reserve_capture=0.08,
    ),
}


@dataclass
class SyntheticPopulation:
    """Columnar person state used by the Twin V2 simulator."""

    person_id: np.ndarray
    join_year: np.ndarray
    birth_year: np.ndarray
    cohort: np.ndarray
    sex: np.ndarray
    retirement_age: np.ndarray
    salary: np.ndarray
    contribution_rate: np.ndarray
    balance: np.ndarray
    piu_balance: np.ndarray
    total_contributions: np.ndarray
    benefits_paid: np.ndarray
    annual_benefit: np.ndarray
    benefit_piu: np.ndarray
    status: np.ndarray

    def size(self) -> int:
        return int(self.person_id.shape[0])

    def ages(self, year: int) -> np.ndarray:
        return np.asarray(year, dtype=np.int64) - self.birth_year

    def append(self, other: "SyntheticPopulation") -> None:
        for field in self.__dataclass_fields__:
            setattr(self, field, np.concatenate((getattr(self, field), getattr(other, field))))


def _style(key: str) -> PopulationStyle:
    return POPULATION_STYLES.get(key, POPULATION_STYLES["balanced"])


def _sample_age_bands(rng: np.random.Generator, n: int, style: PopulationStyle) -> np.ndarray:
    bands = rng.choice(4, size=n, p=style.age_weights)
    ages = np.empty(n, dtype=np.int16)
    masks = [
        bands == 0,
        bands == 1,
        bands == 2,
        bands == 3,
    ]
    if masks[0].any():
        ages[masks[0]] = rng.integers(20, 35, size=int(masks[0].sum()))
    if masks[1].any():
        ages[masks[1]] = rng.integers(35, 50, size=int(masks[1].sum()))
    if masks[2].any():
        ages[masks[2]] = rng.integers(50, 67, size=int(masks[2].sum()))
    if masks[3].any():
        ages[masks[3]] = rng.integers(67, 91, size=int(masks[3].sum()))
    return ages


def _salary_curve(anchor: float, ages: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    peak = np.clip((ages - 22) / 25.0, 0.3, 1.3)
    retirement_drag = np.where(ages > 67, np.clip(1.0 - (ages - 67) * 0.03, 0.35, 1.0), 1.0)
    sigma = 0.33
    base = rng.lognormal(np.log(anchor) - 0.5 * sigma**2, sigma, size=ages.shape[0])
    return np.round(base * peak * retirement_drag, 2)


def generate_population_v2(
    n: int,
    *,
    start_year: int,
    seed: int,
    style_key: str = "balanced",
    id_offset: int = 0,
) -> SyntheticPopulation:
    """Generate a heterogeneous starting society."""
    if n <= 0:
        empty = np.array([], dtype=np.int64)
        empty_f = np.array([], dtype=np.float64)
        empty_i = np.array([], dtype=np.int8)
        return SyntheticPopulation(
            person_id=empty,
            join_year=empty,
            birth_year=empty,
            cohort=empty,
            sex=empty_i,
            retirement_age=empty,
            salary=empty_f,
            contribution_rate=empty_f,
            balance=empty_f,
            piu_balance=empty_f,
            total_contributions=empty_f,
            benefits_paid=empty_f,
            annual_benefit=empty_f,
            benefit_piu=empty_f,
            status=empty_i,
        )

    style = _style(style_key)
    rng = np.random.default_rng(int(seed))
    ages = _sample_age_bands(rng, n, style)
    birth_year = np.asarray(start_year, dtype=np.int64) - ages.astype(np.int64)
    retirement_age = rng.choice(np.array([64, 65, 67, 69]), size=n, p=[0.15, 0.35, 0.35, 0.15]).astype(np.int16)
    sex = rng.choice(np.array([SEX_MALE, SEX_FEMALE], dtype=np.int8), size=n, p=[0.49, 0.51])
    salary = _salary_curve(style.salary_anchor, ages, rng)

    contribution_rate = np.clip(
        rng.normal(style.contribution_mean, 0.018, size=n),
        0.04,
        0.16,
    )

    career_progress = np.clip((ages - 22) / np.maximum(retirement_age - 22, 1), 0.0, 1.3)
    balance_anchor = salary * (2.2 + 10.5 * career_progress**2)
    balance_noise = rng.lognormal(mean=0.0, sigma=0.35, size=n)
    balance = np.round(balance_anchor * balance_noise, 2)
    total_contributions = np.round(np.maximum(balance * (0.70 + 0.35 * rng.random(n)), salary * contribution_rate), 2)
    benefits_paid = np.zeros(n, dtype=np.float64)
    annual_benefit = np.zeros(n, dtype=np.float64)
    benefit_piu = np.zeros(n, dtype=np.float64)
    status = np.full(n, STATUS_ACTIVE, dtype=np.int8)
    piu_balance = np.round(balance.copy(), 4)

    retired = ages >= retirement_age
    status[retired] = STATUS_RETIRED
    annual_benefit[retired] = np.round(np.maximum(balance[retired] * 0.055, salary[retired] * 0.24), 2)
    benefit_piu[retired] = np.round(annual_benefit[retired], 6)
    benefits_paid[retired] = np.round(annual_benefit[retired] * rng.uniform(1.0, 6.0, size=int(retired.sum())), 2)
    piu_balance[retired] = 0.0

    person_id = np.arange(id_offset, id_offset + n, dtype=np.int64)
    join_year = np.full(n, int(start_year), dtype=np.int64)
    cohort = ((birth_year // 5) * 5).astype(np.int64)

    return SyntheticPopulation(
        person_id=person_id,
        join_year=join_year,
        birth_year=birth_year.astype(np.int64),
        cohort=cohort,
        sex=sex,
        retirement_age=retirement_age.astype(np.int64),
        salary=salary.astype(np.float64),
        contribution_rate=contribution_rate.astype(np.float64),
        balance=balance.astype(np.float64),
        piu_balance=piu_balance.astype(np.float64),
        total_contributions=total_contributions.astype(np.float64),
        benefits_paid=benefits_paid.astype(np.float64),
        annual_benefit=annual_benefit.astype(np.float64),
        benefit_piu=benefit_piu.astype(np.float64),
        status=status,
    )


def generate_entrants_v2(
    count: int,
    *,
    year: int,
    rng: np.random.Generator,
    style_key: str,
    id_offset: int,
) -> SyntheticPopulation:
    """Generate new entrants for one simulation year."""
    if count <= 0:
        return generate_population_v2(0, start_year=year, seed=0, style_key=style_key, id_offset=id_offset)

    style = _style(style_key)
    ages = np.clip(rng.normal(29.0, 5.0, size=count), 20, 56).astype(np.int16)
    birth_year = np.asarray(year, dtype=np.int64) - ages.astype(np.int64)
    retirement_age = rng.choice(np.array([64, 65, 67, 69]), size=count, p=[0.12, 0.33, 0.38, 0.17]).astype(np.int16)
    sex = rng.choice(np.array([SEX_MALE, SEX_FEMALE], dtype=np.int8), size=count, p=[0.49, 0.51])
    salary = _salary_curve(style.entrant_salary_anchor, ages, rng)
    contribution_rate = np.clip(rng.normal(style.contribution_mean - 0.005, 0.015, size=count), 0.04, 0.15)

    person_id = np.arange(id_offset, id_offset + count, dtype=np.int64)
    join_year = np.full(count, int(year), dtype=np.int64)
    cohort = ((birth_year // 5) * 5).astype(np.int64)
    empty_f = np.zeros(count, dtype=np.float64)
    status = np.full(count, STATUS_ACTIVE, dtype=np.int8)

    return SyntheticPopulation(
        person_id=person_id,
        join_year=join_year,
        birth_year=birth_year.astype(np.int64),
        cohort=cohort,
        sex=sex,
        retirement_age=retirement_age.astype(np.int64),
        salary=salary.astype(np.float64),
        contribution_rate=contribution_rate.astype(np.float64),
        balance=empty_f.copy(),
        piu_balance=empty_f.copy(),
        total_contributions=empty_f.copy(),
        benefits_paid=empty_f.copy(),
        annual_benefit=empty_f.copy(),
        benefit_piu=empty_f.copy(),
        status=status,
    )


__all__ = [
    "POPULATION_STYLES",
    "PopulationStyle",
    "SEX_FEMALE",
    "SEX_MALE",
    "STATUS_ACTIVE",
    "STATUS_DECEASED",
    "STATUS_RETIRED",
    "SyntheticPopulation",
    "generate_entrants_v2",
    "generate_population_v2",
]
