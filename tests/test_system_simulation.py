"""Tests for engine.system_simulation — the digital-twin driver.

Small-scale runs only (50 members × 5–8 years) so the test suite stays fast.
"""
from __future__ import annotations

from engine.events import DEATH, JOIN, MARKET_CRASH, YEAR_CLOSED
from engine.population import EntrantConfig
from engine.scenarios import (
    SystemConfig,
    get_preset,
    market_crash,
    stable,
)
from engine.system_simulation import (
    SystemResult,
    run_system_simulation,
)


def _tiny_cfg(base: SystemConfig) -> SystemConfig:
    """Shrink a preset so tests run in a fraction of a second."""
    base.n_members = 60
    base.horizon_years = 6
    base.stress_scenarios = 80
    base.entrants = EntrantConfig(mean_per_year=5)
    return base


def test_run_returns_system_result_shape():
    r = run_system_simulation(_tiny_cfg(stable()))
    assert isinstance(r, SystemResult)
    assert len(r.annual) == 6
    assert list(r.annual["year"]) == [2026, 2027, 2028, 2029, 2030, 2031]


def test_annual_has_expected_columns():
    r = run_system_simulation(_tiny_cfg(stable()))
    expected = {
        "year", "active", "retired", "deceased",
        "joined", "retiring", "deaths",
        "total_contrib", "total_benefit", "fund_nav", "reserve",
        "funded_ratio", "mwr_scheme", "gini", "intergen_index",
        "stress_pass_rate", "return",
    }
    assert expected.issubset(set(r.annual.columns))


def test_events_contain_year_closed_per_year():
    r = run_system_simulation(_tiny_cfg(stable()))
    closed = [e for e in r.events if e.kind == YEAR_CLOSED]
    assert len(closed) == r.config.horizon_years


def test_representatives_cover_all_four_profiles():
    r = run_system_simulation(_tiny_cfg(stable()))
    profs = set(r.representative["profile"].unique())
    assert profs == {"young", "mid", "near", "retiree"}


def test_cohort_mwr_long_is_nonempty_and_bounded():
    r = run_system_simulation(_tiny_cfg(stable()))
    assert len(r.cohort_mwr_long) > 0
    assert r.cohort_mwr_long["mwr"].min() >= 0
    assert r.cohort_mwr_long["mwr"].max() < 20  # sanity upper bound


def test_market_crash_scenario_emits_crash_event():
    cfg = _tiny_cfg(market_crash())
    cfg.horizon_years = 10  # crash is at offset 6
    r = run_system_simulation(cfg)
    assert any(e.kind == MARKET_CRASH for e in r.events)


def test_determinism_same_seed_same_result():
    cfg = _tiny_cfg(stable())
    r1 = run_system_simulation(cfg)
    r2 = run_system_simulation(_tiny_cfg(stable()))  # fresh copy, same seed
    # Same seed → identical annual KPIs
    assert list(r1.annual["fund_nav"]) == list(r2.annual["fund_nav"])
    assert list(r1.annual["deaths"]) == list(r2.annual["deaths"])


def test_entrants_flow_increases_population():
    cfg = _tiny_cfg(stable())
    cfg.entrants = EntrantConfig(mean_per_year=10)
    r = run_system_simulation(cfg)
    join_events = [e for e in r.events if e.kind == JOIN]
    assert join_events
    total_joined = sum(e.data.get("count", 0) for e in join_events)
    assert r.final_members >= cfg.n_members + total_joined - 5


def test_deaths_column_matches_death_events():
    cfg = _tiny_cfg(stable())
    cfg.horizon_years = 8
    r = run_system_simulation(cfg)
    # sum of "deaths" column equals total death events over all years
    total_death_events = sum(
        e.data.get("count", 0)
        for e in r.events if e.kind == DEATH
    )
    assert int(r.annual["deaths"].sum()) == int(total_death_events)


def test_every_scenario_preset_runs_without_error():
    """Fast smoke test — each preset must run a few years and produce data."""
    for key in ("stable", "inflation_shock", "market_crash",
                "aging_society", "unfair_reform", "young_stress"):
        cfg = _tiny_cfg(get_preset(key))
        r = run_system_simulation(cfg)
        assert len(r.annual) == cfg.horizon_years
        assert r.events  # must emit something
