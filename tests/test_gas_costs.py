"""Tests for the Option B blockchain execution cost model."""
from __future__ import annotations

import pandas as pd

from engine.gas_costs import (
    build_option_b_twin_counts,
    build_sandbox_option_b_counts,
    fee_gbp_from_wei,
    network_preset_catalog,
    run_gas_cost_model,
)


def _annual_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "year": 2026,
                "population_total": 1000,
                "active_count": 700,
                "retired_count": 200,
                "entrant_count": 40,
                "retirement_count": 25,
                "fund_nav": 45_000_000.0,
                "reserve": 2_500_000.0,
                "contributions": 4_000_000.0,
                "funded_ratio": 0.94,
                "reserve_ratio": 0.052,
                "proposals_generated": 1,
            },
            {
                "year": 2027,
                "population_total": 1015,
                "active_count": 690,
                "retired_count": 220,
                "entrant_count": 35,
                "retirement_count": 28,
                "fund_nav": 44_500_000.0,
                "reserve": 2_200_000.0,
                "contributions": 4_050_000.0,
                "funded_ratio": 0.91,
                "reserve_ratio": 0.047,
                "proposals_generated": 0,
            },
        ]
    )


def test_network_catalog_contains_ethereum_and_base():
    keys = {row["key"] for row in network_preset_catalog()}
    assert {"ethereum", "base", "rollup_low"}.issubset(keys)


def test_twin_counts_include_member_and_governance_actions():
    counts = build_option_b_twin_counts(_annual_frame(), starting_population=1000, cohort_count=8)
    first_year = counts[counts["year"] == 2026]
    lookup = {row["action_key"]: int(row["count"]) for row in first_year.to_dict("records")}
    assert lookup["register_member"] == 1000
    assert lookup["record_contribution"] == 700
    assert lookup["open_retirement"] == 25
    assert lookup["publish_baseline"] == 1
    assert lookup["submit_proposal"] == 1


def test_gas_model_builds_cumulative_totals_and_per_member_metrics():
    counts = build_option_b_twin_counts(_annual_frame(), starting_population=1000, cohort_count=8)
    result = run_gas_cost_model(counts, preset_key="ethereum")
    assert not result.annual.empty
    assert list(result.annual["cumulative_cost_gbp"]) == sorted(result.annual["cumulative_cost_gbp"])
    latest = result.annual.iloc[-1]
    assert latest["cost_per_member_gbp"] > 0
    assert latest["cost_per_1000_members_gbp"] > latest["cost_per_member_gbp"]
    assert result.summary["top_action_type"] in {
        "Oracle updates",
        "Governance",
        "Reserve actions",
        "Member lifecycle",
        "Member cashflows",
    }


def test_base_like_preset_is_cheaper_than_ethereum_like():
    counts = build_option_b_twin_counts(_annual_frame(), starting_population=1000, cohort_count=8)
    eth = run_gas_cost_model(counts, preset_key="ethereum")
    base = run_gas_cost_model(counts, preset_key="base")
    assert eth.summary["total_cost_gbp"] > base.summary["total_cost_gbp"]
    assert eth.summary["latest_cost_per_member_gbp"] > base.summary["latest_cost_per_member_gbp"]


def test_sandbox_counts_cover_full_proof_flow():
    counts = build_sandbox_option_b_counts(member_count=15, cohort_count=4)
    result = run_gas_cost_model(counts, preset_key="base")
    action_keys = {row["action_key"] for row in counts.to_dict("records")}
    assert {
        "register_member",
        "record_contribution",
        "publish_piu_price",
        "publish_mortality_basis",
        "publish_baseline",
        "submit_proposal",
        "publish_stress",
        "fund_reserve",
        "release_reserve",
        "open_retirement",
    }.issubset(action_keys)
    assert result.summary["total_cost_gbp"] > 0


def test_actual_fee_conversion_stays_separate_from_simulated_cost_model():
    # 0.01 ETH in wei
    fee_wei = 10_000_000_000_000_000
    eth_like = fee_gbp_from_wei(fee_wei, "ethereum")
    base_like = fee_gbp_from_wei(fee_wei, "base")
    assert eth_like == base_like


def test_action_type_totals_compute_shares_and_largest_driver():
    counts = build_option_b_twin_counts(_annual_frame(), starting_population=1000, cohort_count=8)
    result = run_gas_cost_model(counts, preset_key="ethereum")
    assert not result.action_type_totals.empty
    assert abs(float(result.action_type_totals["share_of_total_cost"].sum()) - 1.0) < 0.001
    largest = result.action_type_totals.iloc[0]
    assert result.summary["largest_cost_driver"] == largest["action_type"]
    assert result.summary["largest_cost_driver_share"] == largest["share_of_total_cost"]
    assert "example_contract_mapping" in result.action_type_totals.columns
    assert "recommended_execution_strategy" in result.action_type_totals.columns


def test_recommendation_changes_when_governance_is_dominant():
    governance_counts = pd.DataFrame(
        [
            {
                "year": 2026,
                "action_key": "submit_proposal",
                "count": 3,
                "cohort_count": 8,
                "population_total": 1000,
                "retired_count": 100,
                "contributions": 4_000_000.0,
                "assets": 40_000_000.0,
            }
        ]
    )
    result = run_gas_cost_model(governance_counts, preset_key="ethereum")
    assert result.summary["largest_cost_driver"] == "Governance"
    assert "mainnet" in result.summary["recommendation_label"].lower()
    assert result.summary["architecture_status_label"] == "MAINNET ACCEPTABLE"


def test_member_cashflow_dominance_recommends_batching_or_l2():
    counts = pd.DataFrame(
        [
            {
                "year": 2026,
                "action_key": "record_contribution",
                "count": 10_000,
                "cohort_count": 10,
                "population_total": 10_000,
                "retired_count": 1_000,
                "contributions": 50_000_000.0,
                "assets": 500_000_000.0,
            },
            {
                "year": 2026,
                "action_key": "publish_stress",
                "count": 1,
                "cohort_count": 10,
                "population_total": 10_000,
                "retired_count": 1_000,
                "contributions": 50_000_000.0,
                "assets": 500_000_000.0,
            },
        ]
    )
    result = run_gas_cost_model(counts, preset_key="ethereum")
    assert result.summary["largest_cost_driver"] == "Member cashflows"
    assert result.summary["largest_cost_driver_share"] > 0.95
    assert result.summary["architecture_status_label"] == "MAINNET WARNING"
    assert "batch" in result.summary["recommendation_label"].lower()
    assert "L2" in result.summary["recommendation_text"]
