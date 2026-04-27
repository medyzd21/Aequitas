"""Tests for the Digital Twin V2 simulator."""
from __future__ import annotations

from engine.twin_v2 import TwinV2Config, TwinV2Result, baseline_catalog, run_twin_v2


def _tiny_cfg(**kwargs) -> TwinV2Config:
    params = {
        "population_size": 2_000,
        "horizon_years": 6,
        "seed": 7,
        "stress_scenarios": 90,
        "investment_ballot_interval_years": 2,
    }
    params.update(kwargs)
    return TwinV2Config(
        **params,
    )


def test_baseline_catalog_lists_expected_presets():
    keys = {row["key"] for row in baseline_catalog()}
    assert keys == {"healthy", "stress", "governance", "fragile"}


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
        "raw_piu_price",
        "active_pool_nav",
        "total_active_piu_supply",
        "pius_per_1000",
        "indexed_liability",
    }.issubset(result.annual.columns)
    assert {"cohort", "money_worth_ratio", "stress_load", "per_member_epv"}.issubset(result.cohort_metrics.columns)
    assert {"young", "mid", "near", "retiree"} == set(result.personas["key"].unique())
    assert {"piu_balance", "benefit_piu", "nominal_piu_value", "piu_price"}.issubset(result.personas.columns)
    assert {"credibility_weight", "average_multiplier", "study_hash"}.issubset(result.mortality_history.columns)
    assert {"cohort", "blended_multiplier", "observed_expected"}.issubset(result.mortality_basis.columns)
    assert {"active_policy", "policy_next_year", "investment_ballot_status", "policy_expected_return"}.issubset(result.annual.columns)
    assert {"status", "adopted_policy_name", "winning_policy_name"}.issubset(result.investment_ballots.columns)
    assert {"policy_key", "policy_name", "status"}.issubset(result.investment_policy_history.columns)
    assert {"portfolio_name", "row_type", "reason"}.issubset(result.investment_vote_snapshot.columns)
    assert result.investment_summary["summary_text"]
    assert {"total_cost_gbp", "cost_per_member_gbp", "member_cashflows_cost_k"}.issubset(result.gas_annual.columns)
    assert {"label", "action_type", "total_cost_gbp"}.issubset(result.gas_action_breakdown.columns)
    assert {"preset_label", "total_cost_gbp"}.issubset(result.gas_comparison.columns)
    assert result.gas_summary["recommendation_label"]
    assert result.calibration_diagnostics["starting_funded_ratio"] > 0
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
            random_events_enabled=True,
            market_crash=True,
            inflation_shock=True,
            aging_society=True,
            unfair_reform=True,
            young_stress=True,
            event_frequency=2.0,
            event_intensity=1.8,
        )
    )
    assert not result.onchain.empty
    assert {"simulation", "contract", "action", "classification", "detail"}.issubset(result.onchain.columns)
    assert "CohortLedger" in set(result.onchain["contract"])
    assert "MortalityBasisOracle" in set(result.onchain["contract"])
    assert "StressOracle" in set(result.onchain["contract"])
    assert "setPiuPrice" in set(result.onchain["action"])
    assert "PIU price updated" in set(result.events["label"])


def test_investment_ballots_occur_and_use_simulated_active_contributors():
    result = run_twin_v2(_tiny_cfg(horizon_years=8, baseline_key="healthy"))
    assert not result.investment_ballots.empty
    assert "Investment ballot opened" in set(result.events["label"])
    sample_rows = result.investment_vote_snapshot[result.investment_vote_snapshot["row_type"] == "voter_sample"]
    assert not sample_rows.empty
    assert (sample_rows["weighted_votes"] > 0).all()
    assert (sample_rows["voter_count"] >= 0).all()
    assert (sample_rows["voter_count"] > 0).any()


def test_ballot_winner_can_be_blocked_by_guardrails():
    result = run_twin_v2(
        _tiny_cfg(
            baseline_key="fragile",
            horizon_years=10,
            random_events_enabled=True,
            market_crash=True,
            inflation_shock=True,
            aging_society=True,
            unfair_reform=True,
            young_stress=True,
            event_frequency=1.9,
            event_intensity=1.6,
        )
    )
    assert "Investment policy blocked" in set(result.events["label"])
    blocked = result.investment_ballots[result.investment_ballots["status"] == "Blocked"]
    assert not blocked.empty


def test_adopted_policy_changes_later_year_outcomes():
    common = {
        "baseline_key": "governance",
        "horizon_years": 10,
        "seed": 3,
        "random_events_enabled": True,
        "aging_society": True,
        "unfair_reform": True,
        "young_stress": True,
        "event_frequency": 1.2,
        "event_intensity": 1.0,
    }
    with_voting = run_twin_v2(
        _tiny_cfg(
            **common,
        )
    )
    without_voting = run_twin_v2(
        _tiny_cfg(
            **common,
            investment_voting_enabled=False,
        )
    )
    assert list(with_voting.annual["active_policy"]) != list(without_voting.annual["active_policy"])
    assert list(with_voting.annual["fund_nav"]) != list(without_voting.annual["fund_nav"])


def test_investment_governance_is_deterministic_for_same_seed():
    a = run_twin_v2(_tiny_cfg(horizon_years=8, baseline_key="healthy", seed=21))
    b = run_twin_v2(_tiny_cfg(horizon_years=8, baseline_key="healthy", seed=21))
    assert a.investment_ballots.to_dict("records") == b.investment_ballots.to_dict("records")
    assert a.investment_vote_snapshot.to_dict("records") == b.investment_vote_snapshot.to_dict("records")


def test_healthy_baseline_does_not_immediately_collapse():
    result = run_twin_v2(
        _tiny_cfg(
            baseline_key="healthy",
            horizon_years=8,
            random_events_enabled=False,
            market_crash=False,
            inflation_shock=False,
            aging_society=False,
            unfair_reform=False,
            young_stress=False,
        )
    )
    assert 0.85 <= float(result.annual["funded_ratio"].iloc[0]) <= 1.25
    assert float(result.annual["funded_ratio"].min()) > 0.75
    assert float(result.annual["stress_pass_rate"].mean()) > 0.70
    assert result.proposals.empty
    assert "Balanced" in set(result.annual["active_policy_name"])


def test_stress_preset_is_visibly_worse_than_healthy_baseline():
    healthy = run_twin_v2(_tiny_cfg(baseline_key="healthy", horizon_years=8, random_events_enabled=False))
    stress = run_twin_v2(
        _tiny_cfg(
            baseline_key="stress",
            horizon_years=8,
            random_events_enabled=True,
            market_crash=True,
            inflation_shock=True,
            aging_society=True,
            unfair_reform=True,
            young_stress=True,
            event_frequency=1.8,
            event_intensity=1.5,
        )
    )
    assert float(stress.annual["funded_ratio"].min()) < float(healthy.annual["funded_ratio"].min())
    assert len(stress.events) > len(healthy.events)


def test_governance_challenge_triggers_governance_event():
    result = run_twin_v2(
        _tiny_cfg(
            baseline_key="governance",
            horizon_years=9,
            random_events_enabled=True,
            aging_society=True,
            unfair_reform=True,
            young_stress=True,
            event_frequency=1.2,
            event_intensity=1.0,
        )
    )
    assert not result.proposals.empty
    assert "FairnessGate" in set(result.proposals["contract"])


def test_twin_v2_fairness_metrics_stay_in_readable_ranges():
    result = run_twin_v2(_tiny_cfg(baseline_key="healthy", horizon_years=8, random_events_enabled=False))
    assert float(result.cohort_metrics["money_worth_ratio"].max()) < 5.0
    assert float(result.annual["gini"].max()) < 0.30
    assert result.annual["stress_pass_rate"].between(0.0, 1.0).all()
    assert result.annual["funded_ratio"].between(0.0, 3.0).all()
