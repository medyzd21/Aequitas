"""Option B blockchain execution cost model.

This module estimates what Aequitas would cost if a broader set of
protocol actions were executed on-chain. It is intentionally explicit and
static: no live RPC lookups, no fee-oracle dependency, and no claim that
these are exact quotes. The goal is product and architecture judgment.

Design choices:
* Costs are driven by declared action counts and declared gas profiles.
* Network presets are "all-in effective fee" assumptions expressed in
  gwei, plus a reference ETH/GBP rate so costs can be compared with
  pension cashflows in the UI.
* The model is for blockchain execution only. It does not price private
  actuarial work, raw data handling, or off-chain computation.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd


WEI_PER_ETH = 10**18


@dataclass(frozen=True)
class GasActionProfile:
    key: str
    label: str
    action_type: str
    actor_type: str
    contract_function: str
    gas_units: int
    per_cohort_gas_units: int = 0
    note: str = ""


@dataclass(frozen=True)
class GasNetworkPreset:
    key: str
    label: str
    all_in_gas_price_gwei: float
    eth_price_gbp: float
    description: str
    layer_recommendation: str


@dataclass
class GasSimulationResult:
    preset: GasNetworkPreset
    annual: pd.DataFrame
    action_breakdown: pd.DataFrame
    action_totals: pd.DataFrame
    actor_totals: pd.DataFrame
    preset_comparison: pd.DataFrame
    summary: dict[str, Any]
    assumptions: list[str]


ACTION_PROFILES: dict[str, GasActionProfile] = {
    "publish_piu_price": GasActionProfile(
        key="publish_piu_price",
        label="Publish CPI-linked PIU price",
        action_type="Oracle updates",
        actor_type="Actuary",
        contract_function="CohortLedger.setPiuPrice",
        gas_units=55_000,
        note="One CPI-linked PIU price publication each year.",
    ),
    "publish_mortality_basis": GasActionProfile(
        key="publish_mortality_basis",
        label="Publish mortality basis snapshot",
        action_type="Oracle updates",
        actor_type="Actuary",
        contract_function="MortalityBasisOracle.publishBasis",
        gas_units=199_000,
        note="One versioned mortality basis snapshot each year.",
    ),
    "publish_stress": GasActionProfile(
        key="publish_stress",
        label="Publish fairness stress result",
        action_type="Oracle updates",
        actor_type="Actuary",
        contract_function="StressOracle.updateStressLevel",
        gas_units=105_000,
        note="One stress publication per year.",
    ),
    "publish_baseline": GasActionProfile(
        key="publish_baseline",
        label="Publish cohort baseline",
        action_type="Governance",
        actor_type="Governance",
        contract_function="FairnessGate.setBaseline",
        gas_units=125_000,
        per_cohort_gas_units=9_000,
        note="Initial fairness baseline plus cohort vector write cost.",
    ),
    "submit_proposal": GasActionProfile(
        key="submit_proposal",
        label="Submit governance proposal",
        action_type="Governance",
        actor_type="Governance",
        contract_function="FairnessGate.submitAndEvaluate",
        gas_units=185_000,
        per_cohort_gas_units=11_000,
        note="Proposal evaluation cost scales with cohort comparisons.",
    ),
    "fund_reserve": GasActionProfile(
        key="fund_reserve",
        label="Fund reserve vault",
        action_type="Reserve actions",
        actor_type="Treasury",
        contract_function="BackstopVault.deposit",
        gas_units=46_000,
        note="Treasury top-up after a reserve draw or visibly thin buffer.",
    ),
    "release_reserve": GasActionProfile(
        key="release_reserve",
        label="Release reserve",
        action_type="Reserve actions",
        actor_type="Treasury",
        contract_function="BackstopVault.release",
        gas_units=200_000,
        note="Reserve release when a shortfall hits pension cashflows.",
    ),
    "register_member": GasActionProfile(
        key="register_member",
        label="Register member",
        action_type="Member lifecycle",
        actor_type="Members",
        contract_function="CohortLedger.registerMember",
        gas_units=115_000,
        note="One on-chain registration per newly on-boarded member.",
    ),
    "record_contribution": GasActionProfile(
        key="record_contribution",
        label="Record contribution",
        action_type="Member cashflows",
        actor_type="Members",
        contract_function="CohortLedger.contribute",
        gas_units=188_000,
        note="One contribution-recording transaction per active contributor per year.",
    ),
    "open_retirement": GasActionProfile(
        key="open_retirement",
        label="Open retirement flow",
        action_type="Member lifecycle",
        actor_type="Members",
        contract_function="VestaRouter.openRetirement",
        gas_units=150_000,
        note="One retirement-opening transaction per new retiree.",
    ),
}


NETWORK_PRESETS: dict[str, GasNetworkPreset] = {
    "ethereum": GasNetworkPreset(
        key="ethereum",
        label="Ethereum-like",
        all_in_gas_price_gwei=28.0,
        eth_price_gbp=2_600.0,
        description="A mainnet-style all-in execution fee assumption. Useful for asking whether broad member-level posting is realistic under expensive blockspace.",
        layer_recommendation="Ethereum-like",
    ),
    "base": GasNetworkPreset(
        key="base",
        label="Base-like",
        all_in_gas_price_gwei=0.12,
        eth_price_gbp=2_600.0,
        description="A lower-cost L2-style assumption including a simplified allowance for rollup data costs. Useful for asking whether broader execution becomes operationally viable on an L2.",
        layer_recommendation="Base-like",
    ),
    "rollup_low": GasNetworkPreset(
        key="rollup_low",
        label="Low-cost rollup",
        all_in_gas_price_gwei=0.03,
        eth_price_gbp=2_600.0,
        description="A very low-cost rollup-style assumption for sensitivity analysis. Helpful for showing where execution cost stops being a strategic blocker.",
        layer_recommendation="Low-cost rollup",
    ),
}


def action_profile_catalog() -> list[dict[str, str]]:
    return [
        {
            "key": profile.key,
            "label": profile.label,
            "action_type": profile.action_type,
            "actor_type": profile.actor_type,
            "contract_function": profile.contract_function,
            "note": profile.note,
        }
        for profile in ACTION_PROFILES.values()
    ]


def network_preset_catalog() -> list[dict[str, str]]:
    return [
        {
            "key": preset.key,
            "label": preset.label,
            "description": preset.description,
        }
        for preset in NETWORK_PRESETS.values()
    ]


def _preset(preset_key: str) -> GasNetworkPreset:
    return NETWORK_PRESETS.get(preset_key, NETWORK_PRESETS["ethereum"])


def gas_units_for_action(action_key: str, cohort_count: int = 0) -> int:
    profile = ACTION_PROFILES[action_key]
    cohorts = max(0, int(cohort_count))
    return int(profile.gas_units + profile.per_cohort_gas_units * cohorts)


def fee_eth_from_gas(gas_units: int, preset_key: str) -> float:
    preset = _preset(preset_key)
    return float(gas_units) * preset.all_in_gas_price_gwei * 1e-9


def fee_gbp_from_gas(gas_units: int, preset_key: str) -> float:
    preset = _preset(preset_key)
    return fee_eth_from_gas(gas_units, preset_key) * preset.eth_price_gbp


def fee_eth_from_wei(fee_wei: int | str) -> float:
    return float(int(fee_wei)) / WEI_PER_ETH


def fee_gbp_from_wei(fee_wei: int | str, preset_key: str) -> float:
    return fee_eth_from_wei(fee_wei) * _preset(preset_key).eth_price_gbp


def build_option_b_twin_counts(
    annual: pd.DataFrame,
    *,
    starting_population: int,
    cohort_count: int,
) -> pd.DataFrame:
    """Declare the Option B transaction counts implied by a Twin run.

    Assumptions are explicit:
    * one PIU price publication, one mortality-basis publication, and one
      stress publication per year
    * one fairness baseline publication at inception
    * one contribution-recording transaction per active member per year
    * one member registration per entrant, plus initial registrations
    * one retirement-opening transaction per retiree transition
    * reserve release if the reserve visibly falls year-on-year
    * reserve deposit the following year if the prior year released reserve
    """
    if annual.empty:
        return pd.DataFrame()

    rows: list[dict[str, Any]] = []
    previous_reserve = None
    previous_release = 0
    for idx, row in annual.sort_values("year").iterrows():
        year = int(row["year"])
        active = max(0, int(row["active_count"]))
        retired = max(0, int(row["retired_count"]))
        contributions = max(0.0, float(row["contributions"]))
        assets = max(0.0, float(row["fund_nav"]))
        reserve = max(0.0, float(row["reserve"]))
        released = 0
        if previous_reserve is not None:
            reserve_drop = previous_reserve - reserve
            if reserve_drop > max(25_000.0, previous_reserve * 0.05):
                released = 1
        funded_ratio = float(row.get("funded_ratio", 1.0))
        reserve_ratio = float(row.get("reserve_ratio", 0.0))
        reserve_fund = 1 if previous_release and funded_ratio >= 0.85 else 0
        if reserve_ratio < 0.03 and funded_ratio >= 0.95:
            reserve_fund = max(reserve_fund, 1)

        action_counts = {
            "publish_piu_price": 1,
            "publish_mortality_basis": 1,
            "publish_stress": 1,
            "publish_baseline": 1 if idx == annual.index.min() else 0,
            "submit_proposal": max(0, int(row.get("proposals_generated", 0) or 0)),
            "fund_reserve": reserve_fund,
            "release_reserve": released,
            "register_member": max(0, starting_population if idx == annual.index.min() else int(row.get("entrant_count", 0) or 0)),
            "record_contribution": active,
            "open_retirement": max(0, int(row.get("retirement_count", 0) or 0)),
        }
        for action_key, count in action_counts.items():
            rows.append(
                {
                    "year": year,
                    "action_key": action_key,
                    "count": int(count),
                    "cohort_count": int(cohort_count),
                    "population_total": max(1, int(row["population_total"])),
                    "retired_count": max(1, retired),
                    "contributions": contributions,
                    "assets": assets,
                }
            )
        previous_reserve = reserve
        previous_release = released
    return pd.DataFrame(rows)


def build_sandbox_option_b_counts(
    *,
    member_count: int,
    cohort_count: int,
) -> pd.DataFrame:
    """Declare the deterministic sandbox proof-flow counts."""
    steps = [
        ("register_member", member_count),
        ("record_contribution", member_count),
        ("publish_piu_price", 1),
        ("publish_mortality_basis", 1),
        ("publish_baseline", 1),
        ("submit_proposal", 1),
        ("publish_stress", 1),
        ("fund_reserve", 1),
        ("release_reserve", 1),
        ("open_retirement", 1),
    ]
    return pd.DataFrame(
        [
            {
                "year": 1,
                "action_key": action_key,
                "count": int(count),
                "cohort_count": int(cohort_count),
                "population_total": max(1, int(member_count)),
                "retired_count": max(1, min(int(member_count), 3)),
                "contributions": float(member_count) * 5_000.0,
                "assets": float(member_count) * 35_000.0,
                "step_order": idx,
            }
            for idx, (action_key, count) in enumerate(steps, start=1)
        ]
    )


def _price_counts(counts: pd.DataFrame, preset_key: str) -> pd.DataFrame:
    if counts.empty:
        return pd.DataFrame()
    preset = _preset(preset_key)
    rows: list[dict[str, Any]] = []
    for row in counts.to_dict("records"):
        action_key = str(row["action_key"])
        profile = ACTION_PROFILES[action_key]
        gas_each = gas_units_for_action(action_key, int(row.get("cohort_count", 0)))
        count = max(0, int(row["count"]))
        total_gas = gas_each * count
        total_cost_eth = fee_eth_from_gas(total_gas, preset.key)
        total_cost_gbp = total_cost_eth * preset.eth_price_gbp
        rows.append(
            {
                **row,
                "label": profile.label,
                "action_type": profile.action_type,
                "actor_type": profile.actor_type,
                "contract_function": profile.contract_function,
                "gas_units_each": gas_each,
                "total_gas_units": total_gas,
                "total_cost_eth": total_cost_eth,
                "total_cost_gbp": total_cost_gbp,
                "note": profile.note,
            }
        )
    return pd.DataFrame(rows)


def _recommendation(summary: dict[str, Any], preset: GasNetworkPreset) -> tuple[str, str]:
    share = float(summary.get("total_share_contributions", 0.0))
    latest_per_member = float(summary.get("latest_cost_per_member_gbp", 0.0))
    member_share = float(summary.get("member_execution_share", 0.0))
    if preset.key == "ethereum" and (share >= 0.02 or latest_per_member >= 5.0):
        return (
            "Move broad member-level execution to an L2 such as Base.",
            "Under this fee model, direct member-level posting is doing enough damage to contributions that the protocol should keep selective publication on expensive blockspace and move granular execution to an L2.",
        )
    if share >= 0.008 or latest_per_member >= 1.0:
        return (
            "Selective publication is still the safer default.",
            "The protocol logic works, but this level of on-chain activity is still material enough that selective publication remains the cleaner choice unless an L2 is explicitly part of the production design.",
        )
    if preset.key == "base" and member_share >= 0.5:
        return (
            "Base-like execution looks operationally viable.",
            "Most of the simulated cost is still coming from member-level posting, but this fee model keeps it small enough that a broader on-chain architecture can be defended.",
        )
    return (
        f"{preset.layer_recommendation} execution looks acceptable.",
        "At this fee level the blockchain cost stays small relative to the pension cashflows being modelled, so execution cost is no longer the main architectural blocker.",
    )


def run_gas_cost_model(
    counts: pd.DataFrame,
    *,
    preset_key: str,
) -> GasSimulationResult:
    priced = _price_counts(counts, preset_key)
    preset = _preset(preset_key)
    if priced.empty:
        return GasSimulationResult(
            preset=preset,
            annual=pd.DataFrame(),
            action_breakdown=pd.DataFrame(),
            action_totals=pd.DataFrame(),
            actor_totals=pd.DataFrame(),
            preset_comparison=pd.DataFrame(),
            summary={},
            assumptions=[],
        )

    annual = (
        priced.groupby("year", as_index=False)
        .agg(
            total_gas_units=("total_gas_units", "sum"),
            total_cost_eth=("total_cost_eth", "sum"),
            total_cost_gbp=("total_cost_gbp", "sum"),
            population_total=("population_total", "max"),
            retired_count=("retired_count", "max"),
            contributions=("contributions", "max"),
            assets=("assets", "max"),
        )
        .sort_values("year")
    )
    annual["cumulative_cost_gbp"] = annual["total_cost_gbp"].cumsum()
    annual["cumulative_cost_eth"] = annual["total_cost_eth"].cumsum()
    annual["cost_per_member_gbp"] = annual["total_cost_gbp"] / annual["population_total"].clip(lower=1)
    annual["cost_per_1000_members_gbp"] = annual["cost_per_member_gbp"] * 1_000.0
    annual["cost_per_retiree_gbp"] = annual["total_cost_gbp"] / annual["retired_count"].clip(lower=1)
    annual["cost_share_contributions"] = annual["total_cost_gbp"] / annual["contributions"].clip(lower=1.0)
    annual["cost_share_assets"] = annual["total_cost_gbp"] / annual["assets"].clip(lower=1.0)
    annual["total_cost_k"] = annual["total_cost_gbp"] / 1_000.0
    annual["cumulative_cost_k"] = annual["cumulative_cost_gbp"] / 1_000.0

    by_type = (
        priced.groupby(["year", "action_type"], as_index=False)
        .agg(total_cost_gbp=("total_cost_gbp", "sum"))
    )
    for action_type in sorted(priced["action_type"].unique()):
        slug = action_type.lower().replace(" ", "_")
        values = by_type.loc[by_type["action_type"] == action_type, ["year", "total_cost_gbp"]]
        lookup = {int(row["year"]): float(row["total_cost_gbp"]) for row in values.to_dict("records")}
        annual[f"{slug}_cost_gbp"] = [lookup.get(int(year), 0.0) for year in annual["year"]]
        annual[f"{slug}_cost_k"] = annual[f"{slug}_cost_gbp"] / 1_000.0

    action_totals = (
        priced.groupby(["action_key", "label", "action_type", "actor_type", "contract_function"], as_index=False)
        .agg(
            count=("count", "sum"),
            total_gas_units=("total_gas_units", "sum"),
            total_cost_eth=("total_cost_eth", "sum"),
            total_cost_gbp=("total_cost_gbp", "sum"),
        )
        .sort_values("total_cost_gbp", ascending=False)
    )
    actor_totals = (
        priced.groupby(["actor_type", "action_type"], as_index=False)
        .agg(total_cost_gbp=("total_cost_gbp", "sum"))
        .sort_values("total_cost_gbp", ascending=False)
    )

    comparison_rows: list[dict[str, Any]] = []
    for network_key, network in NETWORK_PRESETS.items():
        alt = _price_counts(counts, network_key)
        total_cost_gbp = float(alt["total_cost_gbp"].sum())
        latest_year = (
            alt.groupby("year", as_index=False)
            .agg(total_cost_gbp=("total_cost_gbp", "sum"), contributions=("contributions", "max"), population_total=("population_total", "max"))
            .sort_values("year")
            .tail(1)
        )
        latest_cost = float(latest_year["total_cost_gbp"].iloc[0]) if not latest_year.empty else 0.0
        latest_population = float(latest_year["population_total"].iloc[0]) if not latest_year.empty else 1.0
        latest_share = (
            float(latest_year["total_cost_gbp"].iloc[0]) / max(float(latest_year["contributions"].iloc[0]), 1.0)
            if not latest_year.empty else 0.0
        )
        comparison_rows.append(
            {
                "preset_key": network.key,
                "preset_label": network.label,
                "description": network.description,
                "total_cost_gbp": round(total_cost_gbp, 2),
                "total_cost_k": round(total_cost_gbp / 1_000.0, 2),
                "latest_cost_gbp": round(latest_cost, 2),
                "latest_cost_per_member_gbp": round(latest_cost / max(latest_population, 1.0), 4),
                "latest_share_contributions_pct": round(latest_share * 100.0, 3),
            }
        )
    preset_comparison = pd.DataFrame(comparison_rows).sort_values("total_cost_gbp", ascending=False)

    latest = annual.iloc[-1]
    top_action = action_totals.iloc[0] if not action_totals.empty else None
    member_share = (
        float(
            action_totals.loc[
                action_totals["action_type"].isin(["Member cashflows", "Member lifecycle"]),
                "total_cost_gbp",
            ].sum()
        ) / max(float(action_totals["total_cost_gbp"].sum()), 1.0)
    )
    summary = {
        "total_cost_gbp": float(annual["total_cost_gbp"].sum()),
        "cumulative_cost_gbp": float(annual["cumulative_cost_gbp"].iloc[-1]),
        "latest_cost_gbp": float(latest["total_cost_gbp"]),
        "latest_cost_per_member_gbp": float(latest["cost_per_member_gbp"]),
        "latest_cost_per_1000_members_gbp": float(latest["cost_per_1000_members_gbp"]),
        "latest_cost_per_retiree_gbp": float(latest["cost_per_retiree_gbp"]),
        "total_share_contributions": float(annual["total_cost_gbp"].sum() / max(float(annual["contributions"].sum()), 1.0)),
        "latest_share_contributions": float(latest["cost_share_contributions"]),
        "latest_share_assets": float(latest["cost_share_assets"]),
        "top_action_label": str(top_action["label"]) if top_action is not None else "",
        "top_action_type": str(top_action["action_type"]) if top_action is not None else "",
        "top_action_cost_gbp": float(top_action["total_cost_gbp"]) if top_action is not None else 0.0,
        "member_execution_share": float(member_share),
    }
    recommendation_label, recommendation_text = _recommendation(summary, preset)
    summary["recommendation_label"] = recommendation_label
    summary["recommendation_text"] = recommendation_text

    assumptions = [
        "Option B counts blockchain execution only. It does not count private data ingestion, actuarial calibration, or off-chain model fitting.",
        "Each active contributor is assumed to post one on-chain contribution transaction per year. That is the main driver of cost in the on-chain-heavy scenario.",
        "The model includes annual oracle publications, initial baseline publication, proposal submissions, retirement openings, member registrations, and reserve actions when the simulated reserve visibly moves.",
        "Network presets use explicit all-in effective fee assumptions rather than live RPC estimates, so the comparison stays stable and explainable in a jury demo.",
    ]

    return GasSimulationResult(
        preset=preset,
        annual=annual.reset_index(drop=True),
        action_breakdown=priced.reset_index(drop=True),
        action_totals=action_totals.reset_index(drop=True),
        actor_totals=actor_totals.reset_index(drop=True),
        preset_comparison=preset_comparison.reset_index(drop=True),
        summary=summary,
        assumptions=assumptions,
    )


__all__ = [
    "ACTION_PROFILES",
    "NETWORK_PRESETS",
    "GasActionProfile",
    "GasNetworkPreset",
    "GasSimulationResult",
    "action_profile_catalog",
    "build_option_b_twin_counts",
    "build_sandbox_option_b_counts",
    "fee_eth_from_gas",
    "fee_eth_from_wei",
    "fee_gbp_from_gas",
    "fee_gbp_from_wei",
    "gas_units_for_action",
    "network_preset_catalog",
    "run_gas_cost_model",
]
