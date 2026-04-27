"""Regression checks for Twin V2 investment-governance state wiring."""
from __future__ import annotations

import pytest

pytest.importorskip("reflex")

from reflex_app.aequitas_rx.state import (
    AppState,
    _build_twin_v2_fairness_verdict,
    _build_twin_v2_focus_cohort_rows,
    _build_twin_v2_worst_cohort_rows,
)


def test_twin_v2_state_serializes_investment_governance_outputs():
    state = AppState()
    state.twin_v2_population_size = 2_000
    state.twin_v2_horizon_years = 8
    state.twin_v2_seed = 11
    state.twin_v2_investment_voting_enabled = True
    state.twin_v2_investment_ballot_interval_years = 2

    state.run_twin_v2_simulation()

    assert state.twin_v2_investment_summary_text
    assert state.twin_v2_investment_ballot_count >= 1
    assert state.twin_v2_active_policy_name
    assert state.twin_v2_investment_ballot_rows
    assert state.twin_v2_investment_policy_rows
    assert state.twin_v2_investment_onchain_rows
    assert isinstance(state.twin_v2_investment_vote_snapshot_rows, list)
    assert state.twin_v2_calibration_rows
    assert any(row["metric"] == "Starting funded ratio" for row in state.twin_v2_calibration_rows)
    assert any(row["metric"] == "Portfolio guardrail note" for row in state.twin_v2_calibration_rows)


def test_twin_v2_cohort_fairness_rows_are_readable_mwr_ratios():
    rows, note = _build_twin_v2_focus_cohort_rows(
        [
            {
                "cohort": 1980,
                "members": 120,
                "epv_contributions": 1000.0,
                "epv_benefits": 1120.0,
                "money_worth_ratio": 112.0,  # percent-style upstream accident
                "year": 2036,
                "stress_load": 0.0,
                "per_member_epv": 100.0,
                "members_k": 0.12,
            },
            {
                "cohort": 1990,
                "members": 140,
                "epv_contributions": 1000.0,
                "epv_benefits": 910.0,
                "money_worth_ratio": 9100.0,  # bps-style upstream accident
                "year": 2036,
                "stress_load": 0.0,
                "per_member_epv": 100.0,
                "members_k": 0.14,
            },
            {
                "cohort": 1940,
                "members": 30,
                "epv_contributions": 0.01,
                "epv_benefits": 10_000.0,
                "money_worth_ratio": 1_000_000.0,
                "year": 2036,
                "stress_load": 0.0,
                "per_member_epv": 100.0,
                "members_k": 0.03,
            },
        ],
        limit=10,
    )

    assert [row["money_worth_ratio"] for row in rows] == [1.12, 0.91]
    assert rows[0]["mwr_display"] == "1.12"
    assert rows[0]["fairness_status"] == "Watch"
    assert rows[1]["fairness_status_detail"] == "Moderately below parity"
    assert all(0 <= row["money_worth_ratio"] <= 2.0 for row in rows)
    assert "extreme or non-ratio" in note


def test_twin_v2_run_exposes_presentation_ready_cohort_fairness_rows():
    state = AppState()
    state.twin_v2_population_size = 2_000
    state.twin_v2_horizon_years = 6
    state.twin_v2_seed = 15

    state.run_twin_v2_simulation()

    assert state.twin_v2_focus_cohort_rows
    for row in state.twin_v2_focus_cohort_rows:
        assert 0 <= row["money_worth_ratio"] <= 2.0
        assert row["mwr_display"]
        assert row["fairness_status"] in {"Balanced", "Watch", "Stress"}
        assert "mwr_balanced" in row
        assert "mwr_watch" in row
        assert "mwr_stress" in row


def test_twin_v2_fairness_verdict_and_worst_hit_rows_are_presentation_ready():
    latest_rows = [
        {
            "cohort": 1980,
            "money_worth_ratio": 1.01,
            "stress_load": 0.02,
            "year": 2036,
        },
        {
            "cohort": 1995,
            "money_worth_ratio": 0.88,
            "stress_load": 0.18,
            "year": 2036,
        },
    ]
    worst = _build_twin_v2_worst_cohort_rows(latest_rows)
    verdict = _build_twin_v2_fairness_verdict(
        [{"gini": 0.13, "intergen_index": 0.74, "stress_pass_rate": 0.52}],
        worst,
        proposal_count=1,
    )

    assert worst[0]["cohort"] == 1995
    assert worst[0]["mwr_display"] == "0.88"
    assert worst[0]["stress_load_display"] == "18.0%"
    assert worst[0]["status"] == "Stress"
    assert "actuarial parity" in worst[0]["reason"]
    assert verdict["verdict"] == "FAIL"
    assert verdict["gap"] == "13.0%"
    assert verdict["intergen"] == "74.0%"
    assert verdict["stress"] == "52.0%"
    assert "FairnessGate.submitAndEvaluate" in verdict["trigger"]


def test_twin_v2_run_exposes_fairness_presentation_state():
    state = AppState()
    state.twin_v2_population_size = 2_000
    state.twin_v2_horizon_years = 6
    state.twin_v2_seed = 19

    state.run_twin_v2_simulation()

    assert state.twin_v2_fairness_verdict in {"PASS", "WATCH", "FAIL"}
    assert state.twin_v2_fairness_reason
    assert state.twin_v2_fairness_gap_text.endswith("%")
    assert state.twin_v2_intergen_balance_text.endswith("%")
    assert state.twin_v2_stress_pass_text.endswith("%")
    assert state.twin_v2_worst_cohort_rows
    assert state.twin_v2_worst_cohort_rows[0]["reason"]
    assert state.twin_v2_governance_trigger_status in {"Triggered", "Not triggered"}


def test_twin_v2_run_exposes_execution_cost_driver_rows():
    state = AppState()
    state.twin_v2_population_size = 2_000
    state.twin_v2_horizon_years = 6
    state.twin_v2_seed = 23

    state.run_twin_v2_simulation()

    assert state.twin_v2_gas_driver_rows
    assert state.twin_v2_gas_main_driver
    assert state.twin_v2_gas_main_driver_share > 0
    assert state.twin_v2_gas_architecture_status
    assert abs(sum(row["share_of_cost"] for row in state.twin_v2_gas_driver_rows) - 1.0) < 0.001
    assert all(row["recommended_execution_strategy"] for row in state.twin_v2_gas_driver_rows)
    assert all(row["example_contract_mapping"] for row in state.twin_v2_gas_driver_rows)
