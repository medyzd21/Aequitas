"""Tests for the vectorized Digital Twin V2 population engine."""
from __future__ import annotations

import numpy as np

from engine.population_v2 import (
    STATUS_ACTIVE,
    STATUS_RETIRED,
    SyntheticPopulation,
    generate_entrants_v2,
    generate_population_v2,
)


def test_generate_population_v2_shape_and_ranges():
    pop = generate_population_v2(500, start_year=2026, seed=42, style_key="balanced")
    assert isinstance(pop, SyntheticPopulation)
    assert pop.size() == 500
    ages = pop.ages(2026)
    assert ages.min() >= 20
    assert ages.max() <= 90
    assert set(np.unique(pop.status)).issubset({STATUS_ACTIVE, STATUS_RETIRED})
    assert np.all((0.04 <= pop.contribution_rate) & (pop.contribution_rate <= 0.16))
    assert np.all(pop.cohort == (pop.birth_year // 5) * 5)


def test_generate_population_v2_is_deterministic():
    a = generate_population_v2(120, start_year=2026, seed=7, style_key="fragile")
    b = generate_population_v2(120, start_year=2026, seed=7, style_key="fragile")
    assert np.array_equal(a.birth_year, b.birth_year)
    assert np.array_equal(a.retirement_age, b.retirement_age)
    assert np.array_equal(a.salary, b.salary)
    assert np.array_equal(a.balance, b.balance)
    assert np.array_equal(a.piu_balance, b.piu_balance)


def test_generate_entrants_v2_appends_cleanly():
    base = generate_population_v2(50, start_year=2026, seed=11, style_key="growth")
    rng = np.random.default_rng(5)
    entrants = generate_entrants_v2(
        8,
        year=2029,
        rng=rng,
        style_key="growth",
        id_offset=base.size(),
    )
    base.append(entrants)
    assert base.size() == 58
    assert np.all(base.join_year[-8:] == 2029)
    assert np.all(base.person_id[-8:] >= 50)
