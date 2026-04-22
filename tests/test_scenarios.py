"""Tests for engine.scenarios — scenario preset catalogue."""
from __future__ import annotations

import pytest

from engine.scenarios import (
    PRESETS,
    ScheduledProposal,
    ScheduledShock,
    SystemConfig,
    get_preset,
    list_presets,
)


EXPECTED_KEYS = {
    "stable", "inflation_shock", "market_crash",
    "aging_society", "unfair_reform", "young_stress",
}


def test_all_expected_presets_registered():
    assert EXPECTED_KEYS.issubset(PRESETS.keys())


def test_every_preset_builds_valid_config():
    for key in PRESETS:
        cfg = get_preset(key)
        assert isinstance(cfg, SystemConfig)
        assert cfg.name == key
        assert cfg.description, f"{key} needs a description"
        assert cfg.horizon_years > 0
        assert cfg.n_members > 0
        assert 0 < cfg.corridor_delta < 1
        assert 0 < cfg.mean_return < 1


def test_get_preset_returns_fresh_copy():
    a = get_preset("stable")
    b = get_preset("stable")
    a.name = "mutated"
    assert b.name == "stable"


def test_unknown_preset_raises():
    with pytest.raises(ValueError):
        get_preset("does_not_exist")


def test_list_presets_shape():
    entries = list_presets()
    keys = {e["key"] for e in entries}
    assert EXPECTED_KEYS.issubset(keys)
    for e in entries:
        assert set(e) >= {"key", "name", "description"}


def test_market_crash_schedules_shock():
    cfg = get_preset("market_crash")
    assert any(s.kind == "market_crash" for s in cfg.shocks)
    assert cfg.backstop_initial > 0


def test_inflation_shock_schedules_two_shocks():
    cfg = get_preset("inflation_shock")
    assert len(cfg.shocks) >= 2
    assert all(s.kind == "inflation_shock" for s in cfg.shocks)


def test_unfair_reform_has_proposal_targeting_youngest():
    cfg = get_preset("unfair_reform")
    assert cfg.proposals
    prop = cfg.proposals[0]
    assert "YOUNGEST" in prop.multipliers
    assert prop.multipliers["YOUNGEST"] < 1.0


def test_aging_society_shrinks_entrants_and_loosens_mortality():
    baseline = get_preset("stable")
    aged = get_preset("aging_society")
    assert aged.entrants.mean_per_year < baseline.entrants.mean_per_year
    assert aged.mortality_multiplier < baseline.mortality_multiplier


def test_scheduled_dataclasses_store_offset_correctly():
    s = ScheduledShock(offset=3, kind="market_crash", magnitude=0.2)
    assert s.offset == 3
    p = ScheduledProposal(offset=5, name="T", multipliers={"YOUNGEST": 0.9})
    assert p.offset == 5
    assert p.multipliers["YOUNGEST"] == 0.9
