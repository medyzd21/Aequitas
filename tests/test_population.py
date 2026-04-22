"""Tests for engine.population — the synthetic population generator."""
from __future__ import annotations

import numpy as np

from engine.population import (
    EntrantConfig,
    PopulationConfig,
    draw_entrants,
    generate_population,
)


def test_generate_returns_empty_for_nonpositive_n():
    assert generate_population(0, start_year=2026) == []
    assert generate_population(-5, start_year=2026) == []


def test_generate_count_matches():
    pop = generate_population(100, start_year=2026, seed=7)
    assert len(pop) == 100


def test_generate_is_deterministic():
    a = generate_population(50, start_year=2026, seed=123)
    b = generate_population(50, start_year=2026, seed=123)
    assert [m.wallet for m in a] == [m.wallet for m in b]
    assert [m.salary for m in a] == [m.salary for m in b]
    assert [m.birth_year for m in a] == [m.birth_year for m in b]


def test_generate_fields_are_plausible():
    cfg = PopulationConfig()
    pop = generate_population(500, start_year=2026, seed=42, cfg=cfg)
    assert all(cfg.age_at_start_min
               <= (2026 - m.birth_year)
               <= cfg.age_at_start_max
               for m in pop)
    assert all(0.03 <= m.contribution_rate <= 0.15 for m in pop)
    assert all(m.retirement_age in cfg.retirement_age_choices for m in pop)
    assert all(m.sex in ("F", "M") for m in pop)
    # salary sanity — no zeros, no absurd values
    assert all(m.salary > 0 for m in pop)
    assert np.median([m.salary for m in pop]) < 500_000


def test_generate_cohort_rule_applied():
    # cohort should always be floor(birth_year / 5) * 5
    pop = generate_population(50, start_year=2026, seed=1)
    for m in pop:
        assert m.cohort == (m.birth_year // 5) * 5
        assert m.cohort % 5 == 0


def test_generate_wallet_uniqueness():
    pop = generate_population(200, start_year=2026, seed=3)
    wallets = [m.wallet for m in pop]
    assert len(set(wallets)) == len(wallets)


def test_draw_entrants_count_distribution():
    rng = np.random.default_rng(42)
    cfg = EntrantConfig(mean_per_year=20)
    totals = []
    for y in range(10):
        totals.append(len(draw_entrants(rng, 2030 + y, cfg)))
    assert min(totals) >= 0
    # 10 draws averaging 20 — sum should be within ±50% of 200
    assert 100 < sum(totals) < 320


def test_draw_entrants_empty_when_mean_zero():
    rng = np.random.default_rng(0)
    cfg = EntrantConfig(mean_per_year=0)
    assert draw_entrants(rng, 2030, cfg) == []


def test_draw_entrants_members_have_valid_shape():
    rng = np.random.default_rng(5)
    cfg = EntrantConfig(mean_per_year=30)
    got = draw_entrants(rng, 2030, cfg, wallet_prefix="0xE",
                        wallet_offset=1000)
    assert got  # almost certainly nonempty
    for m in got:
        assert m.wallet.startswith("0xE_")
        assert m.join_year == 2030
        assert 20 <= (2030 - m.birth_year) <= 55
        assert 0.03 <= m.contribution_rate <= 0.15
        assert m.retirement_age in (65, 67)
