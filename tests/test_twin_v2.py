"""Tests for the Digital Twin V2 simulator."""
from __future__ import annotations

from engine.twin_v2 import TwinV2Config, TwinV2Result, baseline_catalog, run_twin_v2


def _tiny_cfg(**kwargs) -> TwinV2Config:
    params = {
        "population_size": 2_000,
        "horizon_years": 6,
        "seed": 7,
        "stress_scenarios": 90,
    }
    params.update(kwargs)
    return TwinV2Config(
        **params,
    )


def test_baseline_catalog_lists_expected_presets():
    keys = {row["key"] for row in baseline_catalog()}
    assert keys == {"balanced", "growth", "mature", "fragile"}


def test_run_twin_v2_returns_expected_shape():
    result = run_twin_v2(_tiny_cfg())
    assert isinstance(result, TwinV2Result)
    assert len(result.annual) == 6
    assert {
        "year",
        "population_total",
        "fund_nav",
        "funded_ratio",
        "gini",
        "stress_pass_rate",
        "cpi_index",
        "piu_price",
        "pius_per_1000",
        "indexed_liability",
    }.issubset(result.annual.columns)
    assert {"cohort", "money_worth_ratio", "stress_load", "per_member_epv"}.issubset(result.cohort_metrics.columns)
    assert {"young", "mid", "near", "retiree"} == set(result.personas["key"].unique())
    assert {"piu_balance", "benefit_piu", "nominal_piu_value", "piu_price"}.issubset(result.personas.columns)
    assert {"credibility_weight", "average_multiplier", "study_hash"}.issubset(result.mortality_history.columns)
    assert {"cohort", "blended_multiplier", "observed_expected"}.issubset(result.mortality_basis.columns)
    assert {"total_cost_gbp", "cost_per_member_gbp", "member_cashflows_cost_k"}.issubset(result.gas_annual.columns)
    assert {"label", "action_type", "total_cost_gbp"}.issubset(result.gas_action_breakdown.columns)
    assert {"preset_label", "total_cost_gbp"}.issubset(result.gas_comparison.columns)
    assert result.gas_summary["recommendation_label"]
    assert result.performance_note
    assert result.person_level_note
    assert result.cohort_level_note


def test_run_twin_v2_is_deterministic_for_same_seed():
    a = run_twin_v2(_tiny_cfg(baseline_key="fragile", event_frequency=1.4, event_intensity=1.3))
    b = run_twin_v2(_tiny_cfg(baseline_key="fragile", event_frequency=1.4, event_intensity=1.3))
    assert list(a.annual["fund_nav"]) == list(b.annual["fund_nav"])
    assert list(a.annual["death_count"]) == list(b.annual["death_count"])
    assert a.events.to_dict("records") == b.events.to_dict("records")


def test_pressure_run_generates_governance_and_onchain_rows():
    result = run_twin_v2(
        _tiny_cfg(
            baseline_key="fragile",
            horizon_years=10,
            event_frequency=2.0,
            event_intensity=1.8,
        )
    )
    assert not result.onchain.empty
    assert {"simulation", "contract", "action", "classification", "detail"}.issubset(result.onchain.columns)
    assert "FairnessGate" in set(result.onchain["contract"])
    assert "CohortLedger" in set(result.onchain["contract"])
    assert "MortalityBasisOracle" in set(result.onchain["contract"])
    assert "setPiuPrice" in set(result.onchain["action"])
