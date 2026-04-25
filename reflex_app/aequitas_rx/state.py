"""Reactive state for the Aequitas Reflex frontend.

This module is the only place in the Reflex app that touches the Python
actuarial engine. Every engine call funnels through the service helpers
below, and `AppState` holds only picklable derived data (lists, dicts,
scalars) so Reflex can hydrate it cleanly per page load.
"""
from __future__ import annotations

import json
import os
import shlex
import shutil
import socket
import subprocess
import sys
from pathlib import Path
from typing import Any, ClassVar, Mapping

import numpy as np
import pandas as pd
import reflex as rx
from .serialization import typed_records

# --------------------------------------------------------------------------- path
# Make the repo root importable so the engine modules can be reused.
# repo_root / reflex_app / aequitas_rx / state.py  →  repo_root is parents[2]
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_CONTRACTS_DIR = _REPO_ROOT / "contracts"
_IMPORT_BROADCAST_SCRIPT = _REPO_ROOT / "scripts" / "import_broadcast.py"
_LOCAL_BROADCAST_PATH = _CONTRACTS_DIR / "broadcast" / "Deploy.s.sol" / "31337" / "run-latest.json"
_SEPOLIA_BROADCAST_PATH = _CONTRACTS_DIR / "broadcast" / "Deploy.s.sol" / "11155111" / "run-latest.json"
_LOCAL_REGISTRY_PATH = _CONTRACTS_DIR / "deployments" / "local.json"
_SEPOLIA_REGISTRY_PATH = _CONTRACTS_DIR / "deployments" / "sepolia.json"


def _env_flag(name: str) -> bool:
    return str(os.getenv(name, "")).strip().lower() in {"1", "true", "yes", "on"}


def _anvil_reachable(host: str = "127.0.0.1", port: int = 8545, timeout: float = 0.25) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _forge_available() -> bool:
    return shutil.which("forge") is not None


def _sepolia_rpc_value(env: Mapping[str, str]) -> str:
    return str(env.get("SEPOLIA_RPC_URL") or env.get("RPC_URL_SEPOLIA") or "sepolia")


def _local_deploy_command(env: Mapping[str, str]) -> list[str]:
    private_key = str(env.get("ANVIL_PK") or "").strip()
    if not private_key:
        raise ValueError("ANVIL_PK is not set in the backend environment.")
    return [
        "forge",
        "script",
        "script/Deploy.s.sol",
        "--rpc-url",
        "http://127.0.0.1:8545",
        "--private-key",
        private_key,
        "--broadcast",
    ]


def _sepolia_deploy_command(env: Mapping[str, str]) -> list[str]:
    private_key = str(env.get("DEPLOYER_PK") or "").strip()
    if not private_key:
        raise ValueError("DEPLOYER_PK is not set in the backend environment.")
    return [
        "forge",
        "script",
        "script/Deploy.s.sol",
        "--rpc-url",
        _sepolia_rpc_value(env),
        "--private-key",
        private_key,
        "--broadcast",
        "--verify",
    ]


def _import_broadcast_command(broadcast_path: Path, registry_path: Path, chain_id: int, verified: bool = False) -> list[str]:
    cmd = [
        sys.executable,
        str(_IMPORT_BROADCAST_SCRIPT),
        str(broadcast_path),
        str(registry_path),
        "--chain-id",
        str(chain_id),
    ]
    if verified:
        cmd.extend(["--verified", "all"])
    return cmd


def _masked_command(args: list[str], env: Mapping[str, str]) -> str:
    secrets = {
        str(env.get("ANVIL_PK") or "").strip(),
        str(env.get("DEPLOYER_PK") or "").strip(),
    }
    masked = ["[REDACTED]" if arg in secrets and arg else arg for arg in args]
    return shlex.join(masked)


def _run_subprocess(args: list[str], cwd: Path, env: Mapping[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=str(cwd),
        env=dict(env) if env is not None else None,
        capture_output=True,
        text=True,
        check=False,
    )

# --------------------------------------------------------------------------- engine
from engine import actuarial as act  # noqa: E402
from engine.actuarial_proof import (  # noqa: E402
    build_default_proof_bundle,
    default_method_versions,
)
from engine.chain_bridge import (  # noqa: E402
    calls_to_json,
    encode_actuarial_method_register,
    encode_actuarial_parameter_set_publish,
    encode_actuarial_result_bundle_publish,
    encode_actuarial_scheme_summary_publish,
    encode_actuarial_valuation_snapshot_publish,
    encode_actuarial_mwr_spot_check,
    encode_backstop_deposit,
    encode_backstop_release,
    encode_baseline,
    encode_create_investment_ballot,
    encode_finalize_investment_ballot,
    encode_investment_ballot_weights,
    encode_investment_vote,
    encode_mortality_basis_publish,
    encode_open_retirement,
    encode_piu_price_update,
    encode_pool_deposit,
    encode_proposal,
    encode_stress_update,
    ledger_to_chain_calls,
    normalize_address,
)
from engine.chain_stub import EventLog  # noqa: E402
from engine.deployments import load_latest  # noqa: E402
from engine.experience_oracle import deterministic_sandbox_snapshot  # noqa: E402
from engine.onchain_registry import (  # noqa: E402
    LOCAL_ANVIL_CHAIN_ID,
    SEPOLIA_CHAIN_ID,
    ContractRecord,
    OnchainRegistry,
    chain_name as _chain_name,
    etherscan_address,
    etherscan_tx,
    is_sepolia as _is_sepolia,
    load_any_deployment,
    load_registry,
    short_address,
)
from engine.fairness import (  # noqa: E402
    evaluate_proposal,
    intergenerational_index,
    mwr_dispersion,
    mwr_gini,
)
from engine.fairness_stress import (  # noqa: E402
    build_cohort_betas,
    stochastic_cohort_stress,
)
from engine.gas_costs import (  # noqa: E402
    build_option_b_twin_counts,
    build_sandbox_option_b_counts,
    fee_eth_from_wei,
    fee_gbp_from_gas,
    fee_gbp_from_wei,
    gas_units_for_action,
    network_preset_catalog,
    run_gas_cost_model,
)
from engine.investment_policy import (  # noqa: E402
    MAX_EFFECTIVE_SHARE,
    MIN_VOTERS_FOR_STRICT_CAP,
    build_ballot_draft,
    compute_vote_snapshot,
    portfolio_catalog as investment_portfolio_catalog,
)
from engine.ledger import CohortLedger  # noqa: E402
from engine.models import Proposal  # noqa: E402
from engine.personas import persona_catalog  # noqa: E402
from engine.projection import project_fund, project_member  # noqa: E402
from engine.scenarios import get_preset, list_presets  # noqa: E402
from engine.seed import seed_ledger  # noqa: E402
from engine.system_simulation import run_system_simulation  # noqa: E402
from engine.twin_v2 import (  # noqa: E402
    TwinV2Config,
    baseline_catalog,
    run_twin_v2,
)


# --------------------------------------------------------------------------- service layer
# A single ledger + event log instance lives at module scope — Phase 1 is a
# single-user demo. Phase 2 will move to per-session state.
_LEDGER: CohortLedger | None = None
_EVENT_LOG: EventLog | None = None


def _ledger() -> CohortLedger:
    global _LEDGER
    if _LEDGER is None:
        _LEDGER = CohortLedger(piu_price=1.0, current_cpi=108.0, expected_inflation=0.02)
    return _LEDGER


def _event_log() -> EventLog:
    global _EVENT_LOG
    if _EVENT_LOG is None:
        _EVENT_LOG = EventLog()
    return _EVENT_LOG


def _pretty_event(e) -> str:
    t = e.event_type
    d = e.data or {}
    if t == "demo_data_loaded":
        return f"Demo dataset loaded — {d.get('members', '?')} members seeded."
    if t == "member_registered":
        return (f"Member {d.get('wallet', '?')} registered "
                f"(birth year {d.get('birth_year', '?')}).")
    if t == "contribution_recorded":
        amt = d.get("amount", 0) or 0
        piu = d.get("piu_minted", 0) or 0
        return (f"Contribution from {d.get('wallet', '?')} — "
                f"{amt:,.0f} recorded, {piu:.2f} PIUs minted.")
    if t == "piu_price_updated":
        return (
            f"PIU price updated from CPI — CPI {d.get('cpi', '?')} set the live PIU price to "
            f"{d.get('piu_price', '?')}."
        )
    if t == "proposal_evaluated":
        name = d.get("name", "Proposal")
        verdict = "PASSED corridor" if d.get("passes") else "FAILED corridor"
        g0 = d.get("gini_before", 0) or 0
        g1 = d.get("gini_after", 0) or 0
        return (f"Proposal '{name}' {verdict} — "
                f"Gini {g0:.3f} → {g1:.3f}.")
    if t == "fairness_stress_run":
        return (f"Fairness stress — {d.get('n_scenarios', '?')} scenarios, "
                f"corridor pass {(d.get('corridor_pass_rate', 0) or 0):.0%}.")
    if t == "bridge_handoff":
        return (f"Bridge hand-off — {d.get('calls', '?')} calls across "
                f"{d.get('cohorts', '?')} cohorts.")
    if t == "tx_submitted":
        return f"Transaction submitted — {d.get('hash', '?')}."
    if t == "tx_confirmed":
        return f"Transaction confirmed on Sepolia — {d.get('hash', '?')}."
    if t == "twin_v2_simulation_run":
        return (
            f"Digital Twin V2 run — {d.get('baseline', '?')} baseline, "
            f"{d.get('members', '?')} members, {d.get('years', '?')} years."
        )
    return f"{t}"


def _compact_number(value: float) -> str:
    n = float(value)
    sign = "-" if n < 0 else ""
    magnitude = abs(n)
    if magnitude >= 1_000_000_000:
        return f"{sign}{magnitude / 1_000_000_000:.1f}b"
    if magnitude >= 1_000_000:
        return f"{sign}{magnitude / 1_000_000:.1f}m"
    if magnitude >= 1_000:
        return f"{sign}{magnitude / 1_000:.1f}k"
    return f"{sign}{magnitude:.0f}"


def _compact_currency(value: float) -> str:
    return f"£{_compact_number(value)}"


def _sample_cohort_keys(rows: list[dict], limit: int = 12) -> list[int]:
    cohorts = sorted({int(row["cohort"]) for row in rows})
    if len(cohorts) <= limit:
        return cohorts
    idxs = np.linspace(0, len(cohorts) - 1, num=limit, dtype=int)
    return [cohorts[int(i)] for i in idxs]


def _event_importance_text(label: str) -> str:
    if label == "Market crash":
        return "A sharp investment loss weakens member balances immediately and can force the scheme into harder choices."
    if label == "Inflation regime":
        return "Higher inflation raises the PIU price, so each nominal contribution buys fewer units while indexed pension promises become more expensive."
    if label == "Aging drift":
        return "The society is slowly getting older, which means fewer contributors relative to pensioners."
    if label == "Young-cohort stress":
        return "Younger workers absorb more pain than older cohorts, so intergenerational fairness becomes a live issue."
    if label == "Unfair reform proposal":
        return "Governance has been pulled in because fairness or funding pressure is no longer comfortable."
    if label == "Experience-based mortality update":
        return "The scheme is learning from its own verified experience instead of relying forever on a fixed prior, so liabilities and fairness comparisons can move even without a market shock."
    if label == "Investment ballot opened":
        return "Active contributors are choosing the next model portfolio, so member governance can shift the fund path without turning the scheme into plutocracy."
    if label == "Investment ballot finalized":
        return "The vote has been tallied and checked against fairness and risk guardrails before any policy can be published."
    if label == "Investment policy adopted":
        return "A new model portfolio will shape later-year return, inflation-hedge, and crash-sensitivity assumptions in the Twin."
    if label == "Investment policy blocked":
        return "The winning vote failed guardrails, so the previous policy stays active instead of letting an unsafe mandate through."
    return "This changes the path of the scheme and may affect funding, fairness, or future governance decisions."


# --------------------------------------------------------------------------- state
class AppState(rx.State):
    """Global state for all pages. Hydrated on every navigation."""

    # ---- scalars --------------------------------------------------------
    loaded: bool = False
    members_count: int = 0
    cohorts_count: int = 0
    epv_c: float = 0.0
    epv_b: float = 0.0
    mwr: float = 0.0
    funded_ratio: float = 0.0
    gini: float = 0.0
    intergen: float = 1.0
    mwr_min: float = 0.0
    mwr_max: float = 0.0
    mwr_std: float = 0.0

    # ---- assumptions (mirrored to sidebar inputs) ----------------------
    valuation_year: int = 2026
    discount_rate: float = 0.03
    investment_return: float = 0.05
    salary_growth: float = 0.02
    current_cpi_index: float = 108.0
    current_piu_price_value: float = 1.08
    expected_inflation: float = 0.02

    # ---- deployment ribbon ---------------------------------------------
    deployment_detected: bool = False
    deployment_owner: str = ""
    deployment_count: int = 0
    deployment_address_rows: list[dict] = []
    devtools_enabled: bool = _env_flag("AEQUITAS_DEVTOOLS")
    devtools_status: str = "idle"
    devtools_message: str = ""
    devtools_logs: str = ""
    devtools_last_command: str = ""
    devtools_target: str = ""
    devtools_registry_mode: str = "auto"
    devtools_can_deploy_local: bool = False
    devtools_can_deploy_sepolia: bool = False
    devtools_anvil_detected: bool = False
    devtools_forge_available: bool = False
    devtools_local_registry_exists: bool = False
    devtools_sepolia_registry_exists: bool = False

    # ---- on-chain registry (sepolia.json) ------------------------------
    # Richer than `deployment_*`. Used by the Actions page + status banner.
    registry_present:    bool       = False
    registry_chain_id:   int        = 0
    registry_chain_name: str        = ""
    registry_deployer:   str        = ""
    registry_deployed_at: str       = ""
    registry_explorer_base: str     = ""
    registry_verified:   bool       = False
    registry_rows:       list[dict] = []     # enriched deployment rows
    registry_on_sepolia: bool       = False  # sepolia.json chain_id == 11155111
    registry_source_path: str       = ""

    # ---- live wallet (MetaMask, browser-side) --------------------------
    wallet_connected: bool = False
    wallet_address:   str  = ""
    wallet_short:     str  = ""    # 0xabcd…1234
    wallet_chain_id:  int  = 0
    wallet_chain_name: str = ""
    wallet_is_sepolia: bool = False
    wallet_status_message: str = "Wallet not connected"
    wallet_last_error: str = ""

    # ---- last on-chain action (live tx lifecycle) ----------------------
    # Values for last_tx_status: "idle" | "pending" | "confirmed" | "failed"
    last_tx_status:        str = "idle"
    last_tx_hash:          str = ""
    last_tx_short:         str = ""
    last_tx_action:        str = ""    # plain-English label
    last_tx_action_key:    str = ""
    last_tx_contract:      str = ""    # e.g. "FairnessGate"
    last_tx_function:      str = ""    # e.g. "submitAndEvaluate"
    last_tx_explorer_url:  str = ""
    last_tx_error:         str = ""
    last_tx_gas_used:      int = 0
    last_tx_fee_wei:       str = ""
    last_tx_fee_eth:       float = 0.0
    last_tx_fee_gbp:       float = 0.0

    # ---- execution cost preset + actual fees --------------------------
    gas_network_preset: str = "ethereum"
    gas_network_rows: list[dict] = []
    actual_fee_rows: list[dict] = []
    actual_fee_total_eth: float = 0.0
    actual_fee_total_gbp: float = 0.0
    actual_fee_tx_count: int = 0

    # ---- confirmation drawer (action-center pre-flight) ----------------
    confirm_open:        bool = False
    confirm_action_key:  str  = ""
    confirm_action_label: str = ""
    confirm_contract:    str  = ""
    confirm_function:    str  = ""
    confirm_summary:     str  = ""
    confirm_actuarial:   str  = ""
    confirm_protocol:    str  = ""
    confirm_reversible:  str  = "No — on-chain actions are final."
    confirm_params_rows: list[dict] = []
    confirm_is_live:     bool = False       # live tx vs bridged/simulated
    confirm_mode_label:  str  = "Off-chain"
    confirm_target_addr: str  = ""
    confirm_advanced_json: str = ""
    confirm_call_args_json: str = ""
    confirm_call_value_wei: str = ""

    # ---- tables --------------------------------------------------------
    member_rows: list[dict] = []
    valuation_rows: list[dict] = []
    cohort_mwr_rows: list[dict] = []
    cohort_epv_rows: list[dict] = []
    cohort_contrib_rows: list[dict] = []
    fund_projection_rows: list[dict] = []
    event_rows: list[dict] = []
    raw_event_rows: list[dict] = []

    # ---- governance sandbox --------------------------------------------
    corridor_delta_pct: int = 5   # stored as % for slider UX
    multipliers: dict[str, float] = {}   # key is str(cohort) for Reflex
    sandbox_verdict: str = ""
    sandbox_is_pass: bool = False
    sandbox_ran: bool = False
    sandbox_comparison_rows: list[dict] = []

    # ---- drill-down ----------------------------------------------------
    selected_wallet: str = ""
    member_projection_rows: list[dict] = []
    member_age: int = 0
    member_first_benefit: float = 0.0
    member_fund_peak: float = 0.0

    # ---- stochastic fairness stress -------------------------------------
    stress_scenarios: int = 2000
    stress_factor_sigma_pct: int = 10     # ×100 so the slider stays integer-only
    stress_idiosyncratic_sigma_pct: int = 3
    stress_generational_slope_pct: int = 50
    stress_corridor_delta_pct: int = 5
    stress_youngest_poor_pct: int = 90    # MWR threshold, ×100
    stress_seed: int = 42
    stress_ran: bool = False
    stress_mean_gini: float = 0.0
    stress_p95_gini: float = 0.0
    stress_mean_index: float = 0.0
    stress_p05_index: float = 0.0
    stress_pass_rate: float = 0.0
    stress_youngest_rate: float = 0.0
    stress_youngest_cohort: int = 0
    stress_worst_rows: list[dict] = []
    stress_beta_rows: list[dict] = []
    stress_gini_hist: list[dict] = []

    # ---- representative-member profile chips ----------------------------
    active_profile: str = ""

    # ---- contract payload previews --------------------------------------
    ledger_payload_preview: list[dict] = []
    baseline_payload: dict = {}
    proposal_payload: dict = {}
    pool_deposit_payload: dict = {}
    open_retirement_payload: dict = {}
    piu_price_payload: dict = {}
    mortality_basis_payload: dict = {}
    stress_update_payload: dict = {}
    backstop_deposit_payload: dict = {}
    backstop_release_payload: dict = {}
    actuarial_method_payload: dict = {}
    actuarial_parameter_payload: dict = {}
    actuarial_valuation_payload: dict = {}
    actuarial_result_payload: dict = {}
    actuarial_spot_check_payload: dict = {}
    sandbox_action_rows: list[dict] = []
    sandbox_recent_tx_rows: list[dict] = []
    sandbox_mortality_rows: list[dict] = []
    sandbox_mortality_summary_rows: list[dict] = []
    sandbox_mortality_basis_version: str = ""
    sandbox_mortality_study_hash: str = ""
    sandbox_mortality_credibility: float = 0.0
    sandbox_mortality_advisory: bool = True
    actuarial_method_rows: list[dict] = []
    actuarial_parameter_rows: list[dict] = []
    actuarial_result_rows: list[dict] = []
    actuarial_verifier_rows: list[dict] = []
    actuarial_proof_scope_rows: list[dict] = []
    actuarial_proof_summary_text: str = ""
    actuarial_method_contract_key: str = ""
    actuarial_result_contract_key: str = ""
    actuarial_method_count: int = 0
    sandbox_gas_step_rows: list[dict] = []
    sandbox_gas_comparison_rows: list[dict] = []
    sandbox_gas_assumption_rows: list[dict] = []
    sandbox_gas_total_cost: float = 0.0
    sandbox_gas_total_gas_units: int = 0
    sandbox_gas_summary_text: str = ""

    # ---- investment policy governance -----------------------------------
    investment_round_name: str = "2026 Strategic allocation ballot"
    investment_round_duration_days: int = 7
    investment_policy_rows: list[dict] = []
    investment_weight_rows: list[dict] = []
    investment_support_rows: list[dict] = []
    investment_validation_rows: list[dict] = []
    investment_ballot_rows: list[dict] = []
    investment_guardrail_rows: list[dict] = []
    investment_assumption_rows: list[dict] = []
    investment_ballot_id: int = 0
    investment_ballot_opens_at: int = 0
    investment_ballot_closes_at: int = 0
    investment_winner_key: str = ""
    investment_winner_name: str = ""
    investment_winner_reason: str = ""
    investment_winner_passes: bool = False
    investment_wallet_eligible: bool = False
    investment_wallet_weight: int = 0
    investment_wallet_weight_share: float = 0.0
    investment_wallet_note: str = ""
    investment_snapshot_note: str = ""
    investment_policy_payload: dict[str, Any] = {}
    investment_weights_payload: dict[str, Any] = {}
    investment_vote_payload: dict[str, Any] = {}
    investment_finalize_payload: dict[str, Any] = {}

    # ---- digital twin ---------------------------------------------------
    twin_scenario:    str  = "stable"
    twin_scenario_description: str = ""
    twin_years:       int  = 30
    twin_n_members:   int  = 1_000
    twin_seed:        int  = 42
    twin_ran:         bool = False

    # scenario catalogue (static, filled on first refresh)
    twin_scenario_rows: list[dict] = []

    # time-series outputs
    twin_annual_rows:           list[dict] = []
    twin_cohort_pivot_rows:     list[dict] = []   # { year, "1965": mwr, ... }
    twin_cohort_keys:           list[str]  = []
    twin_event_rows:            list[dict] = []
    twin_event_summary_rows:    list[dict] = []
    twin_rep_young_rows:        list[dict] = []
    twin_rep_mid_rows:          list[dict] = []
    twin_rep_near_rows:         list[dict] = []
    twin_rep_retiree_rows:      list[dict] = []

    # summary scalars
    twin_final_members:    int   = 0
    twin_final_retirees:   int   = 0
    twin_final_deceased:   int   = 0
    twin_peak_nav:         float = 0.0
    twin_peak_nav_year:    int   = 0
    twin_final_funded_ratio: float = 0.0
    twin_avg_gini:         float = 0.0
    twin_avg_intergen:     float = 1.0
    twin_total_contrib:    float = 0.0
    twin_total_benefit:    float = 0.0
    twin_final_reserve:    float = 0.0
    twin_event_count:      int   = 0
    twin_crashes_count:    int   = 0
    twin_proposals_count:  int   = 0

    # ---- digital twin v2 -----------------------------------------------
    twin_v2_population_size: int = 10_000
    twin_v2_horizon_years: int = 30
    twin_v2_seed: int = 42
    twin_v2_baseline_key: str = "balanced"
    twin_v2_baseline_description: str = ""
    twin_v2_random_events_enabled: bool = True
    twin_v2_market_crash: bool = True
    twin_v2_inflation_shock: bool = True
    twin_v2_aging_society: bool = True
    twin_v2_unfair_reform: bool = True
    twin_v2_young_stress: bool = True
    twin_v2_investment_voting_enabled: bool = True
    twin_v2_investment_ballot_interval_years: int = 4
    twin_v2_event_frequency: float = 1.0
    twin_v2_event_intensity: float = 1.0
    twin_v2_ran: bool = False

    # catalogue + presentation controls
    twin_v2_baseline_rows: list[dict] = []
    twin_v2_population_mode: str = "absolute"
    twin_v2_fund_view: str = "assets"
    twin_v2_fairness_view: str = "equity"
    twin_v2_story_key: str = "young"
    twin_v2_cohort_focus_note: str = ""

    # v2 outputs
    twin_v2_annual_rows: list[dict] = []
    twin_v2_cohort_rows: list[dict] = []
    twin_v2_focus_cohort_rows: list[dict] = []
    twin_v2_event_rows: list[dict] = []
    twin_v2_event_mix_rows: list[dict] = []
    twin_v2_proposal_rows: list[dict] = []
    twin_v2_onchain_rows: list[dict] = []
    twin_v2_persona_catalog_rows: list[dict] = []
    twin_v2_story_summary_rows: list[dict] = []
    twin_v2_story_young_rows: list[dict] = []
    twin_v2_story_mid_rows: list[dict] = []
    twin_v2_story_near_rows: list[dict] = []
    twin_v2_story_retiree_rows: list[dict] = []
    twin_v2_selected_story_rows: list[dict] = []
    twin_v2_selected_story: dict[str, Any] = {}
    twin_v2_selected_story_note: str = ""
    twin_v2_selected_story_status_note: str = ""
    twin_v2_run_summary: str = ""
    twin_v2_run_highlights: list[dict] = []
    twin_v2_event_story_rows: list[dict] = []
    twin_v2_reserve_interventions: int = 0
    twin_v2_assumption_rows: list[dict] = []
    twin_v2_model_scope_rows: list[dict] = []

    # v2 summary scalars
    twin_v2_final_population: int = 0
    twin_v2_final_active: int = 0
    twin_v2_final_retired: int = 0
    twin_v2_final_deceased: int = 0
    twin_v2_average_age: float = 0.0
    twin_v2_average_salary: float = 0.0
    twin_v2_final_nav: float = 0.0
    twin_v2_final_reserve: float = 0.0
    twin_v2_final_funded_ratio: float = 0.0
    twin_v2_final_cpi_index: float = 0.0
    twin_v2_final_piu_price: float = 0.0
    twin_v2_final_indexed_liability: float = 0.0
    twin_v2_final_pius_per_1000: float = 0.0
    twin_v2_final_accrued_pius: float = 0.0
    twin_v2_final_pension_units: float = 0.0
    twin_v2_average_gini: float = 0.0
    twin_v2_average_stress_pass: float = 0.0
    twin_v2_event_count: int = 0
    twin_v2_proposal_count: int = 0
    twin_v2_performance_note: str = ""
    twin_v2_person_level_note: str = ""
    twin_v2_cohort_level_note: str = ""
    twin_v2_mortality_rows: list[dict] = []
    twin_v2_mortality_basis_rows: list[dict] = []
    twin_v2_mortality_summary_rows: list[dict] = []
    twin_v2_mortality_basis_version: str = ""
    twin_v2_mortality_credibility: float = 0.0
    twin_v2_mortality_average_multiplier: float = 1.0
    twin_v2_mortality_study_hash: str = ""
    twin_v2_mortality_effect_text: str = ""
    twin_v2_investment_summary_text: str = ""
    twin_v2_investment_ballot_rows: list[dict] = []
    twin_v2_investment_policy_rows: list[dict] = []
    twin_v2_investment_vote_snapshot_rows: list[dict] = []
    twin_v2_investment_effect_rows: list[dict] = []
    twin_v2_investment_onchain_rows: list[dict] = []
    twin_v2_investment_ballot_count: int = 0
    twin_v2_investment_adopted_count: int = 0
    twin_v2_investment_blocked_count: int = 0
    twin_v2_active_policy_name: str = ""
    twin_v2_gas_annual_rows: list[dict] = []
    twin_v2_gas_action_rows: list[dict] = []
    twin_v2_gas_comparison_rows: list[dict] = []
    twin_v2_gas_assumption_rows: list[dict] = []
    twin_v2_gas_scope_rows: list[dict] = []
    twin_v2_gas_total_cost: float = 0.0
    twin_v2_gas_latest_year_cost: float = 0.0
    twin_v2_gas_latest_cost_per_member: float = 0.0
    twin_v2_gas_latest_cost_per_1000: float = 0.0
    twin_v2_gas_total_share_contributions: float = 0.0
    twin_v2_gas_top_action_type: str = ""
    twin_v2_gas_recommendation_label: str = ""
    twin_v2_gas_recommendation_text: str = ""

    # ======================================================================
    # Event handlers
    # ======================================================================
    def refresh_view(self):
        """Called on every page load — keeps state fresh across navigation.

        Not named `hydrate` because recent Reflex versions reserve that
        identifier for internal client-state sync.
        """
        self._refresh()

    def _set_devtools_result(
        self,
        *,
        status: str,
        target: str,
        message: str,
        logs: str = "",
        command: str = "",
    ) -> None:
        self.devtools_status = status
        self.devtools_target = target
        self.devtools_message = message
        self.devtools_logs = logs
        self.devtools_last_command = command

    def _run_devtools_command(
        self,
        *,
        args: list[str],
        cwd: Path,
        target: str,
        success_message: str,
        env: Mapping[str, str] | None = None,
        refresh_after: bool = True,
    ) -> None:
        runtime_env = dict(os.environ if env is None else env)
        command_label = _masked_command(args, runtime_env)
        self._set_devtools_result(
            status="running",
            target=target,
            message=f"Running {target} command…",
            command=command_label,
        )
        try:
            result = _run_subprocess(args, cwd=cwd, env=runtime_env)
        except FileNotFoundError as err:
            self._set_devtools_result(
                status="failed",
                target=target,
                message=f"Command failed to start: {err}",
                logs=str(err),
                command=command_label,
            )
            self._refresh()
            return
        except OSError as err:
            self._set_devtools_result(
                status="failed",
                target=target,
                message=f"Command failed: {err}",
                logs=str(err),
                command=command_label,
            )
            self._refresh()
            return

        combined_logs = "\n".join(
            part for part in [
                result.stdout.strip(),
                result.stderr.strip(),
            ] if part
        )
        if result.returncode == 0:
            self._set_devtools_result(
                status="success",
                target=target,
                message=success_message,
                logs=combined_logs,
                command=command_label,
            )
            if refresh_after:
                self._refresh()
            else:
                self._refresh_registry()
        else:
            self._set_devtools_result(
                status="failed",
                target=target,
                message=f"{target.title()} command failed with exit code {result.returncode}.",
                logs=combined_logs or f"Process exited with {result.returncode}.",
                command=command_label,
            )
            self._refresh()

    def deploy_local_stack(self):
        env = dict(os.environ)
        try:
            args = _local_deploy_command(env)
        except ValueError as err:
            self._set_devtools_result(
                status="failed",
                target="local",
                message=str(err),
            )
            self._refresh()
            return
        self.devtools_registry_mode = "local"
        self._run_devtools_command(
            args=args,
            cwd=_CONTRACTS_DIR,
            target="local",
            success_message="Local stack deployed. Deployment state refreshed from the repo registry.",
            env=env,
        )

    def import_local_broadcast(self):
        if not _LOCAL_BROADCAST_PATH.is_file():
            self._set_devtools_result(
                status="failed",
                target="local",
                message=f"Local broadcast file is missing: {_LOCAL_BROADCAST_PATH}",
            )
            self._refresh()
            return
        self.devtools_registry_mode = "local"
        self._run_devtools_command(
            args=_import_broadcast_command(
                _LOCAL_BROADCAST_PATH,
                _LOCAL_REGISTRY_PATH,
                LOCAL_ANVIL_CHAIN_ID,
            ),
            cwd=_REPO_ROOT,
            target="local",
            success_message="Imported the latest local broadcast and reloaded the deployment registry.",
            env=dict(os.environ),
        )

    def reload_deployment_registry(self):
        self._refresh()
        source = self.registry_source_path or "No deployment registry found"
        self._set_devtools_result(
            status="success",
            target="registry",
            message=f"Deployment registry reloaded from {source}.",
        )

    def deploy_sepolia_stack(self):
        env = dict(os.environ)
        try:
            args = _sepolia_deploy_command(env)
        except ValueError as err:
            self._set_devtools_result(
                status="failed",
                target="sepolia",
                message=str(err),
            )
            self._refresh()
            return
        self.devtools_registry_mode = "sepolia"
        self._run_devtools_command(
            args=args,
            cwd=_CONTRACTS_DIR,
            target="sepolia",
            success_message="Sepolia deployment command completed. Import the latest Sepolia broadcast to refresh the checked-in registry.",
            env=env,
        )

    def import_sepolia_broadcast(self):
        if not _SEPOLIA_BROADCAST_PATH.is_file():
            self._set_devtools_result(
                status="failed",
                target="sepolia",
                message=f"Sepolia broadcast file is missing: {_SEPOLIA_BROADCAST_PATH}",
            )
            self._refresh()
            return
        self.devtools_registry_mode = "sepolia"
        self._run_devtools_command(
            args=_import_broadcast_command(
                _SEPOLIA_BROADCAST_PATH,
                _SEPOLIA_REGISTRY_PATH,
                SEPOLIA_CHAIN_ID,
                verified=True,
            ),
            cwd=_REPO_ROOT,
            target="sepolia",
            success_message="Imported the latest Sepolia broadcast and reloaded the deployment registry.",
            env=dict(os.environ),
        )

    def load_demo(self):
        """Seed the deterministic sandbox dataset."""
        global _LEDGER
        _LEDGER = seed_ledger(CohortLedger(
            piu_price=1.0,
            current_cpi=self.current_cpi_index,
            expected_inflation=self.expected_inflation,
            valuation_year=self.valuation_year,
            discount_rate=self.discount_rate,
            salary_growth=self.salary_growth,
            investment_return=self.investment_return,
        ))
        _event_log().append("demo_data_loaded", members=len(_LEDGER))
        self._refresh()

    # NOTE: Reflex reserves `reset` and auto-generates `set_<var_name>` for
    # every state var, so our custom handlers are renamed to avoid the
    # EventHandlerShadowsBuiltInStateMethodError and auto-setter collisions.
    def reset_demo(self):
        global _LEDGER, _EVENT_LOG
        _LEDGER = CohortLedger(
            piu_price=1.0,
            current_cpi=self.current_cpi_index,
            expected_inflation=self.expected_inflation,
            valuation_year=self.valuation_year,
            discount_rate=self.discount_rate,
            salary_growth=self.salary_growth,
            investment_return=self.investment_return,
        )
        _EVENT_LOG = EventLog()
        self.multipliers = {}
        self.selected_wallet = ""
        self.sandbox_ran = False
        self.sandbox_verdict = ""
        self._refresh()

    def change_valuation_year(self, val):
        try:
            self.valuation_year = int(val)
            led = _ledger()
            led.valuation_year = self.valuation_year
            self._refresh()
        except (TypeError, ValueError):
            pass

    def change_discount_rate(self, val):
        try:
            self.discount_rate = float(val)
            _ledger().discount_rate = self.discount_rate
            self._refresh()
        except (TypeError, ValueError):
            pass

    def change_investment_return(self, val):
        try:
            self.investment_return = float(val)
            _ledger().investment_return = self.investment_return
            self._refresh()
        except (TypeError, ValueError):
            pass

    def change_salary_growth(self, val):
        try:
            self.salary_growth = float(val)
            _ledger().salary_growth = self.salary_growth
            self._refresh()
        except (TypeError, ValueError):
            pass

    def change_current_cpi_index(self, val):
        try:
            self.current_cpi_index = max(1.0, float(val))
            _ledger().set_cpi_level(self.current_cpi_index)
            _event_log().append(
                "piu_price_updated",
                cpi=round(self.current_cpi_index, 3),
                piu_price=round(_ledger().piu_price, 6),
            )
            self._refresh()
        except (TypeError, ValueError):
            pass

    def change_expected_inflation(self, val):
        try:
            self.expected_inflation = max(-0.05, min(0.20, float(val)))
            _ledger().expected_inflation = self.expected_inflation
            _ledger().index_rule = _ledger().index_rule.__class__(
                base_cpi=_ledger().base_cpi,
                base_price=_ledger().index_rule.base_price,
                expected_inflation=self.expected_inflation,
            )
            self._refresh()
        except (TypeError, ValueError):
            pass

    def change_gas_network_preset(self, val):
        preset = str(val or "ethereum")
        if preset not in {row["key"] for row in network_preset_catalog()}:
            preset = "ethereum"
        self.gas_network_preset = preset
        self._refresh_sandbox_gas()
        self._refresh_actual_fee_rows()
        if self.twin_v2_ran and self.twin_v2_annual_rows:
            self._refresh_twin_v2_gas()

    def select_wallet(self, wallet: str):
        self.selected_wallet = wallet
        self._refresh_drilldown()

    def set_corridor_delta(self, val):
        try:
            self.corridor_delta_pct = int(val)
        except (TypeError, ValueError):
            pass

    def set_multiplier(self, cohort_key: str, val):
        try:
            self.multipliers[str(cohort_key)] = float(val)
        except (TypeError, ValueError):
            pass

    def evaluate_sandbox_proposal(self):
        led = _ledger()
        if len(led) < 2:
            self.sandbox_verdict = "Need at least two members to evaluate."
            self.sandbox_is_pass = False
            self.sandbox_ran = True
            return
        cv = led.cohort_valuation()
        mults = {
            int(c): float(self.multipliers.get(str(int(c)), 1.0))
            for c in cv
        }
        delta = self.corridor_delta_pct / 100.0
        outcome = evaluate_proposal(cv, mults, delta=delta)

        self.sandbox_is_pass = bool(outcome["passes"])
        self.sandbox_ran = True
        self.sandbox_verdict = (
            f"{'PASSES' if outcome['passes'] else 'FAILS'} corridor — "
            f"Gini {outcome['gini_before']:.3f} → {outcome['gini_after']:.3f} · "
            f"Intergen {outcome['index_before']:.3f} → {outcome['index_after']:.3f}"
        )
        self.sandbox_comparison_rows = [
            {"cohort": int(c),
             "mwr_before": round(float(outcome["mwr_before"][c]), 4),
             "mwr_after":  round(float(outcome["mwr_after"][c]), 4)}
            for c in sorted(outcome["mwr_before"].keys())
        ]
        _event_log().append(
            "proposal_evaluated",
            name="Governance sandbox",
            multipliers=mults,
            passes=bool(outcome["passes"]),
            gini_before=round(outcome["gini_before"], 4),
            gini_after=round(outcome["gini_after"], 4),
            index_before=round(outcome["index_before"], 4),
            index_after=round(outcome["index_after"], 4),
        )
        self._refresh()

    # ---------------------------------------------------------------- stress
    def change_stress_scenarios(self, val):
        try:
            self.stress_scenarios = max(200, int(val))
        except (TypeError, ValueError):
            pass

    def change_stress_factor_sigma(self, val):
        try:
            self.stress_factor_sigma_pct = max(0, int(val))
        except (TypeError, ValueError):
            pass

    def change_stress_idio_sigma(self, val):
        try:
            self.stress_idiosyncratic_sigma_pct = max(0, int(val))
        except (TypeError, ValueError):
            pass

    def change_stress_slope(self, val):
        try:
            self.stress_generational_slope_pct = max(0, int(val))
        except (TypeError, ValueError):
            pass

    def change_stress_corridor(self, val):
        try:
            self.stress_corridor_delta_pct = max(1, int(val))
        except (TypeError, ValueError):
            pass

    def change_stress_poor(self, val):
        try:
            self.stress_youngest_poor_pct = max(50, int(val))
        except (TypeError, ValueError):
            pass

    def change_stress_seed(self, val):
        try:
            self.stress_seed = int(val)
        except (TypeError, ValueError):
            pass

    def run_stress(self):
        led = _ledger()
        if len(led) == 0:
            self.stress_ran = False
            return
        cv = led.cohort_valuation()
        if len(cv) < 2:
            self.stress_ran = False
            return
        betas = build_cohort_betas(
            sorted(cv.keys()),
            slope=self.stress_generational_slope_pct / 100.0,
        )
        result = stochastic_cohort_stress(
            cv,
            n_scenarios=int(self.stress_scenarios),
            factor_sigma=self.stress_factor_sigma_pct / 100.0,
            idiosyncratic_sigma=self.stress_idiosyncratic_sigma_pct / 100.0,
            betas=betas,
            generational_slope=self.stress_generational_slope_pct / 100.0,
            corridor_delta=self.stress_corridor_delta_pct / 100.0,
            youngest_poor_threshold=self.stress_youngest_poor_pct / 100.0,
            seed=int(self.stress_seed),
        )
        self.stress_mean_gini       = float(result["mean_gini"])
        self.stress_p95_gini        = float(result["p95_gini"])
        self.stress_mean_index      = float(result["mean_index"])
        self.stress_p05_index       = float(result["p05_index"])
        self.stress_pass_rate       = float(result["corridor_pass_rate"])
        self.stress_youngest_rate   = float(result["youngest_poor_rate"])
        self.stress_youngest_cohort = int(result["youngest_cohort"])
        self.stress_beta_rows = [
            {"cohort": int(c), "beta": round(float(b), 4)}
            for c, b in sorted(result["betas"].items())
        ]
        self.stress_worst_rows = [
            {"cohort": int(c),
             "freq": round(float(result["worst_cohort_freq"].get(c, 0.0)), 4)}
            for c in sorted(cv.keys())
        ]
        # Gini histogram binned in Python — Reflex just draws bars.
        series = [float(x) for x in result["gini_series"]]
        if series:
            lo, hi = min(series), max(series)
            if hi <= lo:
                hi = lo + 1e-9
            nbins = 24
            step = (hi - lo) / nbins
            counts = [0] * nbins
            for v in series:
                idx = min(int((v - lo) / step), nbins - 1)
                counts[idx] += 1
            self.stress_gini_hist = [
                {"bin": round(lo + (i + 0.5) * step, 4), "count": int(counts[i])}
                for i in range(nbins)
            ]
        else:
            self.stress_gini_hist = []
        self.stress_ran = True
        _event_log().append(
            "fairness_stress_run",
            n_scenarios=int(self.stress_scenarios),
            corridor_pass_rate=round(float(result["corridor_pass_rate"]), 4),
            mean_gini=round(float(result["mean_gini"]), 4),
            youngest_poor_rate=round(float(result["youngest_poor_rate"]), 4),
        )
        self._refresh_events()

    # ---------------------------------------------------------------- profiles
    def apply_profile(self, key: str):
        """Pick a representative member for the drill-down.

        We compute the choice on the fly from the current roster so the
        mapping keeps working even if the seed changes later.
        """
        self.active_profile = key
        led = _ledger()
        if len(led) == 0:
            return
        members = [(m, led.valuation_year - m.birth_year) for m in led]
        if not members:
            return
        if key == "young":
            chosen = min(members, key=lambda t: t[1])
        elif key == "retiree":
            chosen = max(members, key=lambda t: t[1])
        elif key == "near":
            # closest-to-retirement but not yet past it
            candidates = [t for t in members if t[1] < t[0].retirement_age]
            if candidates:
                chosen = max(candidates, key=lambda t: t[1])
            else:
                chosen = max(members, key=lambda t: t[1])
        else:  # mid-career
            ages = sorted(a for _, a in members)
            median = ages[len(ages) // 2]
            chosen = min(members, key=lambda t: abs(t[1] - median))
        self.selected_wallet = chosen[0].wallet
        self._refresh_drilldown()

    def record_bridge_handoff(self):
        led = _ledger()
        if len(led) == 0:
            return
        cv = led.cohort_valuation()
        calls = ledger_to_chain_calls(led)
        _event_log().append(
            "bridge_handoff",
            calls=len(calls),
            cohorts=len(cv),
            proposal="Contracts preview",
            stress_level=0.25,
        )
        self._refresh()

    # ---------------------------------------------------------------- twin
    def change_twin_scenario(self, val):
        self.twin_scenario = str(val)
        try:
            cfg = get_preset(self.twin_scenario)
            self.twin_scenario_description = cfg.description
        except ValueError:
            self.twin_scenario_description = ""

    def change_twin_years(self, val):
        try:
            self.twin_years = max(5, min(60, int(val)))
        except (TypeError, ValueError):
            pass

    def change_twin_n_members(self, val):
        try:
            self.twin_n_members = max(100, min(10_000, int(val)))
        except (TypeError, ValueError):
            pass

    def change_twin_seed(self, val):
        try:
            self.twin_seed = int(val)
        except (TypeError, ValueError):
            pass

    def run_twin_simulation(self):
        """Run the digital-twin end-to-end and populate every twin_* var."""
        try:
            cfg = get_preset(self.twin_scenario)
        except ValueError:
            return
        cfg.horizon_years = int(self.twin_years)
        cfg.n_members     = int(self.twin_n_members)
        cfg.seed          = int(self.twin_seed)
        # keep stress manageable on UI
        cfg.stress_scenarios = 200

        result = run_system_simulation(cfg)

        # ---- annual KPI rows ---------------------------------------
        self.twin_annual_rows = [
            {k: (int(v) if isinstance(v, (int,)) else (
                    None if v is None else float(v)))
             for k, v in row.items()}
            for row in result.annual.to_dict("records")
        ]

        # ---- cohort MWR pivot (year × cohort → mwr) ----------------
        long = result.cohort_mwr_long
        if not long.empty:
            pivot = long.pivot_table(index="year", columns="cohort",
                                     values="mwr", aggfunc="mean")
            pivot = pivot.sort_index()
            cohort_keys = [str(int(c)) for c in pivot.columns]
            rows = []
            for year, row in pivot.iterrows():
                d: dict[str, Any] = {"year": int(year)}
                for c in pivot.columns:
                    v = row[c]
                    d[str(int(c))] = (
                        None if (v is None or (isinstance(v, float) and v != v))
                        else round(float(v), 4)
                    )
                rows.append(d)
            self.twin_cohort_pivot_rows = rows
            self.twin_cohort_keys = cohort_keys
        else:
            self.twin_cohort_pivot_rows = []
            self.twin_cohort_keys = []

        # ---- representative traces (one list per profile) ----------
        rep = result.representative
        by_prof: dict[str, list[dict]] = {
            "young": [], "mid": [], "near": [], "retiree": [],
        }
        if not rep.empty:
            for row in rep.to_dict("records"):
                prof = row.get("profile")
                if prof in by_prof:
                    by_prof[prof].append({
                        "year":    int(row["year"]),
                        "age":     int(row["age"]),
                        "fund":    round(float(row["fund"]), 2),
                        "benefit": round(float(row["benefit"]), 2),
                        "salary":  round(float(row["salary"]), 2),
                        "status":  str(row["status"]),
                    })
        self.twin_rep_young_rows   = by_prof["young"]
        self.twin_rep_mid_rows     = by_prof["mid"]
        self.twin_rep_near_rows    = by_prof["near"]
        self.twin_rep_retiree_rows = by_prof["retiree"]

        # ---- event timeline ----------------------------------------
        evs = result.events
        self.twin_event_rows = [
            {
                "year":     int(e.year),
                "kind":     str(e.kind),
                "contract": str(e.contract),
                "severity": str(e.severity),
                "message":  str(e.message()),
            }
            for e in evs
        ]
        # summary by kind
        counts: dict[str, int] = {}
        for e in evs:
            counts[e.kind] = counts.get(e.kind, 0) + 1
        self.twin_event_summary_rows = [
            {"kind": k, "count": int(v)}
            for k, v in sorted(counts.items(), key=lambda kv: -kv[1])
        ]

        # ---- summary scalars ---------------------------------------
        annual_df = result.annual
        self.twin_final_members    = int(result.final_members)
        self.twin_final_retirees   = int(result.final_retirees)
        self.twin_final_deceased   = int(result.final_deceased)
        self.twin_event_count      = int(len(evs))
        self.twin_crashes_count    = int(counts.get("market_crash", 0))
        self.twin_proposals_count  = int(counts.get("proposal_evaluated", 0))
        if not annual_df.empty:
            peak_idx = int(annual_df["fund_nav"].idxmax())
            self.twin_peak_nav         = float(annual_df.loc[peak_idx, "fund_nav"])
            self.twin_peak_nav_year    = int(annual_df.loc[peak_idx, "year"])
            self.twin_final_funded_ratio = float(annual_df["funded_ratio"].iloc[-1])
            self.twin_avg_gini         = float(annual_df["gini"].mean())
            self.twin_avg_intergen     = float(annual_df["intergen_index"].mean())
            self.twin_total_contrib    = float(annual_df["total_contrib"].sum())
            self.twin_total_benefit    = float(annual_df["total_benefit"].sum())
            self.twin_final_reserve    = float(annual_df["reserve"].iloc[-1])
        else:
            self.twin_peak_nav = 0.0
            self.twin_peak_nav_year = 0
            self.twin_final_funded_ratio = 0.0
            self.twin_avg_gini = 0.0
            self.twin_avg_intergen = 1.0
            self.twin_total_contrib = 0.0
            self.twin_total_benefit = 0.0
            self.twin_final_reserve = 0.0

        self.twin_ran = True
        _event_log().append(
            "twin_simulation_run",
            scenario=self.twin_scenario,
            years=int(self.twin_years),
            members=int(self.twin_n_members),
            final_members=int(result.final_members),
            crashes=int(counts.get("market_crash", 0)),
        )
        self._refresh_events()

    # ---------------------------------------------------------------- twin v2
    def change_twin_v2_population_size(self, val):
        try:
            self.twin_v2_population_size = max(1_000, min(100_000, int(val)))
        except (TypeError, ValueError):
            pass

    def change_twin_v2_horizon_years(self, val):
        try:
            self.twin_v2_horizon_years = max(1, min(100, int(val)))
        except (TypeError, ValueError):
            pass

    def change_twin_v2_seed(self, val):
        try:
            self.twin_v2_seed = int(val)
        except (TypeError, ValueError):
            pass

    def change_twin_v2_baseline(self, val):
        self.twin_v2_baseline_key = str(val)
        desc = next(
            (row["description"] for row in self.twin_v2_baseline_rows
             if row["key"] == self.twin_v2_baseline_key),
            "",
        )
        self.twin_v2_baseline_description = desc

    def change_twin_v2_random_events_enabled(self, val):
        self.twin_v2_random_events_enabled = bool(val)

    def change_twin_v2_market_crash(self, val):
        self.twin_v2_market_crash = bool(val)

    def change_twin_v2_inflation_shock(self, val):
        self.twin_v2_inflation_shock = bool(val)

    def change_twin_v2_aging_society(self, val):
        self.twin_v2_aging_society = bool(val)

    def change_twin_v2_unfair_reform(self, val):
        self.twin_v2_unfair_reform = bool(val)

    def change_twin_v2_young_stress(self, val):
        self.twin_v2_young_stress = bool(val)

    def change_twin_v2_investment_voting_enabled(self, val):
        self.twin_v2_investment_voting_enabled = bool(val)

    def change_twin_v2_investment_ballot_interval_years(self, val):
        try:
            self.twin_v2_investment_ballot_interval_years = max(2, min(12, int(val)))
        except (TypeError, ValueError):
            pass

    def change_twin_v2_event_frequency(self, val):
        try:
            self.twin_v2_event_frequency = max(0.1, min(3.0, float(val)))
        except (TypeError, ValueError):
            pass

    def change_twin_v2_event_intensity(self, val):
        try:
            self.twin_v2_event_intensity = max(0.1, min(3.0, float(val)))
        except (TypeError, ValueError):
            pass

    def change_twin_v2_population_mode(self, val):
        self.twin_v2_population_mode = str(val)

    def change_twin_v2_fund_view(self, val):
        self.twin_v2_fund_view = str(val)

    def change_twin_v2_fairness_view(self, val):
        self.twin_v2_fairness_view = str(val)

    def _twin_v2_story_rows_for(self, key: str) -> list[dict]:
        if key == "mid":
            return self.twin_v2_story_mid_rows
        if key == "near":
            return self.twin_v2_story_near_rows
        if key == "retiree":
            return self.twin_v2_story_retiree_rows
        return self.twin_v2_story_young_rows

    def _sync_twin_v2_story_selection(self):
        available = {
            row["key"]
            for row in self.twin_v2_story_summary_rows
        }
        selected = self.twin_v2_story_key if self.twin_v2_story_key in available else ""
        if not selected and self.twin_v2_story_summary_rows:
            selected = str(self.twin_v2_story_summary_rows[0]["key"])
        self.twin_v2_story_key = selected or "young"
        self.twin_v2_selected_story_rows = self._twin_v2_story_rows_for(self.twin_v2_story_key)
        self.twin_v2_selected_story = next(
            (
                row for row in self.twin_v2_story_summary_rows
                if str(row["key"]) == self.twin_v2_story_key
            ),
            {},
        )
        if not self.twin_v2_selected_story:
            self.twin_v2_selected_story_note = ""
            self.twin_v2_selected_story_status_note = ""
            return

        selected_rows = self.twin_v2_selected_story_rows
        start_age = int(self.twin_v2_selected_story.get("start_age", 0) or 0)
        retirement_age = int(self.twin_v2_selected_story.get("retirement_age", 0) or 0)
        end_status = str(self.twin_v2_selected_story.get("status", ""))
        retirement_year = self.twin_v2_selected_story.get("retirement_year")
        death_year = self.twin_v2_selected_story.get("death_year")
        if end_status == "Deceased":
            death_line = f"The person dies in {death_year}." if death_year else "The person dies during the run."
            self.twin_v2_selected_story_note = (
                f"This story starts at age {start_age}, targets retirement at {retirement_age}, and ends with the member deceased. "
                f"{death_line} After that point the chart naturally flattens because salary, PIU accumulation, and pension cashflows all stop."
            )
            self.twin_v2_selected_story_status_note = (
                "The flat tail is expected: once the member has died, the simulation stops accruing PIUs and stops paying that persona's indexed pension stream."
            )
        elif end_status == "Retired":
            retirement_line = f"They moved into retirement in {retirement_year}." if retirement_year else "They move into retirement during the run."
            self.twin_v2_selected_story_note = (
                f"This story starts at age {start_age}, reaches retirement age {retirement_age}, and ends in benefit payment mode. "
                f"{retirement_line} The accumulated PIU balance is converted into pension units, so the salary line fades in relevance while indexed pension income becomes the main cashflow."
            )
            self.twin_v2_selected_story_status_note = (
                "A flatter claim path after retirement is normal: new contributions stop, PIU balances are converted, and the pension is paid through indexed pension units."
            )
        else:
            self.twin_v2_selected_story_note = (
                f"This story starts at age {start_age} and remains active through the end of the run. "
                f"The member is still on track toward retirement age {retirement_age}, so the chart focuses on nominal contributions being turned into PIUs."
            )
            self.twin_v2_selected_story_status_note = (
                "This path stays live because the person is still working, buying PIUs, and building future indexed pension rights."
            )
        if selected_rows and len(selected_rows) >= 2:
            last = selected_rows[-1]
            if float(last.get("balance_k", 0.0)) <= 0.05 and end_status in {"Retired", "Deceased"}:
                self.twin_v2_selected_story_status_note += (
                    " Near-zero balances late in the chart do not mean the UI is broken; they reflect benefit drawdown or death."
                )

    def _build_twin_v2_run_summary(self):
        if not self.twin_v2_ran or not self.twin_v2_annual_rows:
            self.twin_v2_run_summary = ""
            self.twin_v2_run_highlights = []
            return
        event_labels = [row["label"] for row in self.twin_v2_event_rows]
        shock_names = []
        for label in ("Market crash", "Inflation regime", "Aging drift", "Young-cohort stress"):
            if label in event_labels:
                shock_names.append(label.lower())
        shock_text = (
            ", ".join(shock_names)
            if shock_names
            else "no major shocks"
        )
        proposals = self.twin_v2_proposal_count
        fairness_state = (
            "stayed broadly fair"
            if self.twin_v2_average_gini <= 0.06 and self.twin_v2_average_stress_pass >= 0.80
            else "showed visible fairness pressure"
            if self.twin_v2_average_gini <= 0.12 and self.twin_v2_average_stress_pass >= 0.55
            else "became stressed and uneven"
        )
        reserve_text = (
            "The reserve had to step in at least once."
            if self.twin_v2_reserve_interventions > 0
            else "The reserve never had to step in."
        )
        mortality_text = (
            f"Mortality learning reached {self.twin_v2_mortality_credibility:.1%} credibility, "
            f"so the active basis moved to about {self.twin_v2_mortality_average_multiplier:.2f}x the baseline hazard."
            if self.twin_v2_mortality_basis_version
            else "Mortality stayed on the baseline prior throughout the run."
        )
        piu_text = (
            f"Ending CPI reached {self.twin_v2_final_cpi_index:.1f}, which set the PIU price to £{self.twin_v2_final_piu_price:.3f}. "
            f"That left roughly {self.twin_v2_final_pius_per_1000:.0f} PIUs purchasable per £1,000 of nominal contribution."
        )
        shocks_on = "with random shocks turned on" if self.twin_v2_random_events_enabled else "with random shocks turned off"
        proposal_text = (
            f"{proposals} governance proposal{'s' if proposals != 1 else ''} were triggered."
            if proposals
            else "No governance proposal was triggered."
        )
        if self.twin_v2_investment_ballot_count:
            investment_text = (
                f"Member investment ballots were simulated in {', '.join(str(int(row['year'])) for row in self.twin_v2_investment_ballot_rows)}. "
                f"{self.twin_v2_investment_adopted_count} winning policy decision{'s' if self.twin_v2_investment_adopted_count != 1 else ''} passed guardrails, "
                f"{self.twin_v2_investment_blocked_count} were blocked, and the active policy ended as {self.twin_v2_active_policy_name or 'the previous policy'}."
            )
        elif self.twin_v2_investment_voting_enabled:
            investment_text = "Investment voting was enabled, but no ballot window opened in this run."
        else:
            investment_text = "Member investment voting was turned off for this run."
        gas_text = (
            f"Under the {next((row['label'] for row in self.gas_network_rows if row['key'] == self.gas_network_preset), self.gas_network_preset)} fee preset, "
            f"Option B on-chain execution would cost about {_compact_currency(self.twin_v2_gas_total_cost)} across the run. "
            f"{self.twin_v2_gas_recommendation_text}"
            if self.twin_v2_gas_total_cost > 0
            else ""
        )
        self.twin_v2_run_summary = (
            f"This run used the {self.twin_v2_baseline_key} preset, simulated {_compact_number(self.twin_v2_population_size)} people "
            f"over {self.twin_v2_horizon_years} years, and ran {shocks_on}. "
            f"During the run we saw {shock_text}. {piu_text} {mortality_text} {investment_text} The scheme {fairness_state}. {proposal_text} {reserve_text} {gas_text}"
        )
        self.twin_v2_run_highlights = [
            {
                "label": "Preset",
                "value": self.twin_v2_baseline_key.replace("_", " ").title(),
            },
            {
                "label": "Population",
                "value": _compact_number(self.twin_v2_population_size),
            },
            {
                "label": "Horizon",
                "value": f"{self.twin_v2_horizon_years} years",
            },
            {
                "label": "Shocks",
                "value": "On" if self.twin_v2_random_events_enabled else "Off",
            },
            {
                "label": "Governance",
                "value": f"{self.twin_v2_proposal_count} triggered",
            },
            {
                "label": "Investment ballots",
                "value": f"{self.twin_v2_investment_ballot_count} simulated",
            },
            {
                "label": "Backstop",
                "value": "Used" if self.twin_v2_reserve_interventions > 0 else "Not used",
            },
            {
                "label": "PIU price",
                "value": f"£{self.twin_v2_final_piu_price:.3f}",
            },
            {
                "label": "£1,000 buys",
                "value": f"{self.twin_v2_final_pius_per_1000:.0f} PIUs",
            },
            {
                "label": "Mortality credibility",
                "value": f"{self.twin_v2_mortality_credibility:.0%}",
            },
            {
                "label": "Execution layer",
                "value": self.twin_v2_gas_recommendation_label or "Review cost tab",
            },
            {
                "label": "Active policy",
                "value": self.twin_v2_active_policy_name or "Not set",
            },
        ]

    def change_twin_v2_story_key(self, val):
        self.twin_v2_story_key = str(val)
        self._sync_twin_v2_story_selection()

    def run_twin_v2_simulation(self):
        cfg = TwinV2Config(
            population_size=int(self.twin_v2_population_size),
            horizon_years=int(self.twin_v2_horizon_years),
            seed=int(self.twin_v2_seed),
            baseline_key=self.twin_v2_baseline_key,
            random_events_enabled=bool(self.twin_v2_random_events_enabled),
            event_frequency=float(self.twin_v2_event_frequency),
            event_intensity=float(self.twin_v2_event_intensity),
            market_crash=bool(self.twin_v2_market_crash),
            inflation_shock=bool(self.twin_v2_inflation_shock),
            aging_society=bool(self.twin_v2_aging_society),
            unfair_reform=bool(self.twin_v2_unfair_reform),
            young_stress=bool(self.twin_v2_young_stress),
            investment_voting_enabled=bool(self.twin_v2_investment_voting_enabled),
            investment_ballot_interval_years=int(self.twin_v2_investment_ballot_interval_years),
            stress_scenarios=140,
        )
        result = run_twin_v2(cfg)

        annual_rows: list[dict[str, Any]] = []
        annual_records = result.annual.to_dict("records")
        first_nav = float(annual_records[0]["fund_nav"]) if annual_records else 1.0
        first_reserve = float(annual_records[0]["reserve"]) if annual_records else 1.0
        first_contrib = max(float(annual_records[0]["contributions"]), 1.0) if annual_records else 1.0
        first_benefit = max(float(annual_records[0]["benefits"]), 1.0) if annual_records else 1.0
        for row in annual_records:
            members = max(int(row["population_total"]), 1)
            society_total = max(
                int(row["active_count"]) + int(row["retired_count"]) + int(row["deceased_count"]),
                1,
            )
            annual_rows.append(
                {
                    "year": int(row["year"]),
                    "population_total": int(row["population_total"]),
                    "active_count": int(row["active_count"]),
                    "retired_count": int(row["retired_count"]),
                    "deceased_count": int(row["deceased_count"]),
                    "entrant_count": int(row["entrant_count"]),
                    "retirement_count": int(row["retirement_count"]),
                    "death_count": int(row["death_count"]),
                    "average_age": float(row["average_age"]),
                    "average_salary": float(row["average_salary"]),
                    "fund_nav": float(row["fund_nav"]),
                    "reserve": float(row["reserve"]),
                    "contributions": float(row["contributions"]),
                    "benefits": float(row["benefits"]),
                    "fund_nav_m": round(float(row["fund_nav"]) / 1_000_000, 3),
                    "reserve_m": round(float(row["reserve"]) / 1_000_000, 3),
                    "contributions_m": round(float(row["contributions"]) / 1_000_000, 3),
                    "benefits_m": round(float(row["benefits"]) / 1_000_000, 3),
                    "nav_per_member": round(float(row["fund_nav"]) / members, 2),
                    "reserve_per_member": round(float(row["reserve"]) / members, 2),
                    "contributions_per_member": round(float(row["contributions"]) / members, 2),
                    "benefits_per_member": round(float(row["benefits"]) / members, 2),
                    "fund_nav_index": round(float(row["fund_nav"]) / max(first_nav, 1.0), 3),
                    "reserve_index": round(float(row["reserve"]) / max(first_reserve, 1.0), 3),
                    "contributions_index": round(float(row["contributions"]) / max(first_contrib, 1.0), 3),
                    "benefits_index": round(float(row["benefits"]) / max(first_benefit, 1.0), 3),
                    "active_share": round(float(row["active_count"]) / society_total, 4),
                    "active_share_pct": round(float(row["active_count"]) * 100.0 / society_total, 2),
                    "retired_share": round(float(row["retired_count"]) / society_total, 4),
                    "retired_share_pct": round(float(row["retired_count"]) * 100.0 / society_total, 2),
                    "deceased_share": round(float(row["deceased_count"]) / society_total, 4),
                    "deceased_share_pct": round(float(row["deceased_count"]) * 100.0 / society_total, 2),
                    "return_rate": float(row["return_rate"]),
                    "inflation_rate": float(row["inflation_rate"]),
                    "funded_ratio": float(row["funded_ratio"]),
                    "funded_ratio_pct": round(float(row["funded_ratio"]) * 100.0, 2),
                    "scheme_mwr": float(row["scheme_mwr"]),
                    "scheme_mwr_pct": round(float(row["scheme_mwr"]) * 100.0, 2),
                    "gini": float(row["gini"]),
                    "gini_pct": round(float(row["gini"]) * 100.0, 2),
                    "intergen_index": float(row["intergen_index"]),
                    "intergen_pct": round(float(row["intergen_index"]) * 100.0, 2),
                    "stress_pass_rate": float(row["stress_pass_rate"]),
                    "stress_pass_pct": round(float(row["stress_pass_rate"]) * 100.0, 2),
                    "stress_p95_gini": float(row["stress_p95_gini"]),
                    "stress_p95_gini_pct": round(float(row["stress_p95_gini"]) * 100.0, 2),
                    "youngest_poor_rate": float(row["youngest_poor_rate"]),
                    "youngest_poor_pct": round(float(row["youngest_poor_rate"]) * 100.0, 2),
                    "event_pressure": float(row["event_pressure"]),
                    "event_pressure_pct": round(float(row["event_pressure"]) * 100.0, 2),
                    "reserve_ratio": float(row["reserve_ratio"]),
                    "reserve_ratio_pct": round(float(row["reserve_ratio"]) * 100.0, 2),
                    "active_policy": str(row.get("active_policy", "balanced")),
                    "active_policy_name": str(row.get("active_policy_name", "Balanced")),
                    "policy_next_year": str(row.get("policy_next_year", row.get("active_policy", "balanced"))),
                    "policy_next_year_name": str(row.get("policy_next_year_name", row.get("active_policy_name", "Balanced"))),
                    "investment_ballot_status": str(row.get("investment_ballot_status", "No ballot")),
                    "policy_expected_return_pct": float(row.get("policy_expected_return_pct", 0.0)),
                    "policy_inflation_hedge_pct": float(row.get("policy_inflation_hedge_pct", 0.0)),
                    "policy_stress_drawdown_pct": float(row.get("policy_stress_drawdown_pct", 0.0)),
                    "policy_fairness_pressure_pct": float(row.get("policy_fairness_pressure_pct", 0.0)),
                    "proposals_generated": int(row["proposals_generated"]),
                    "cpi_index": float(row["cpi_index"]),
                    "piu_price": float(row["piu_price"]),
                    "piu_minted": float(row["piu_minted"]),
                    "accrued_pius": float(row["accrued_pius"]),
                    "pension_units": float(row["pension_units"]),
                    "pius_per_1000": float(row["pius_per_1000"]),
                    "indexed_liability": float(row["indexed_liability"]),
                    "mortality_credibility": float(row.get("mortality_credibility", 0.0)),
                    "mortality_credibility_pct": round(float(row.get("mortality_credibility", 0.0)) * 100.0, 2),
                    "mortality_multiplier": float(row.get("mortality_multiplier", 1.0)),
                    "mortality_multiplier_pct": round((float(row.get("mortality_multiplier", 1.0)) - 1.0) * 100.0, 2),
                    "mortality_observed_expected": float(row.get("mortality_observed_expected", 1.0)),
                }
            )
        if annual_rows:
            first_cpi = max(float(annual_rows[0]["cpi_index"]), 1e-9)
            first_price = max(float(annual_rows[0]["piu_price"]), 1e-9)
            first_units = max(float(annual_rows[0]["pius_per_1000"]), 1e-9)
            for row in annual_rows:
                row["cpi_rebased"] = round(float(row["cpi_index"]) * 100.0 / first_cpi, 2)
                row["piu_price_index"] = round(float(row["piu_price"]) * 100.0 / first_price, 2)
                row["pius_per_1000_index"] = round(float(row["pius_per_1000"]) * 100.0 / first_units, 2)
                row["piu_minted_k"] = round(float(row["piu_minted"]) / 1_000, 3)
                row["accrued_pius_k"] = round(float(row["accrued_pius"]) / 1_000, 3)
                row["pension_units_k"] = round(float(row["pension_units"]) / 1_000, 3)
                row["indexed_liability_m"] = round(float(row["indexed_liability"]) / 1_000_000, 3)
        self.twin_v2_annual_rows = annual_rows

        self.twin_v2_mortality_rows = [
            {
                "year": int(row["year"]),
                "version_id": str(row["version_id"]),
                "credibility_weight": float(row["credibility_weight"]),
                "credibility_pct": float(row["credibility_pct"]),
                "advisory": "Advisory" if bool(row["advisory"]) else "Active",
                "cohort_count": int(row["cohort_count"]),
                "credible_cohort_count": int(row["credible_cohort_count"]),
                "total_exposure_years": float(row["total_exposure_years"]),
                "observed_deaths": int(row["observed_deaths"]),
                "expected_deaths": float(row["expected_deaths"]),
                "observed_expected": float(row["observed_expected"]),
                "average_multiplier": float(row["average_multiplier"]),
                "multiplier_pct": round((float(row["average_multiplier"]) - 1.0) * 100.0, 2),
                "study_hash": str(row["study_hash"]),
            }
            for row in result.mortality_history.to_dict("records")
        ]
        self.twin_v2_mortality_basis_rows = [
            {
                "year": int(row["year"]),
                "version_id": str(row["version_id"]),
                "cohort": int(row["cohort"]),
                "avg_age": float(row["avg_age"]),
                "retired_share_pct": round(float(row["retired_share"]) * 100.0, 2),
                "exposure_years": float(row["exposure_years"]),
                "observed_deaths": int(row["observed_deaths"]),
                "expected_deaths": float(row["expected_deaths"]),
                "observed_expected": float(row["observed_expected"]),
                "credibility_pct": round(float(row["credibility_weight"]) * 100.0, 2),
                "experience_multiplier_pct": round((float(row["experience_multiplier"]) - 1.0) * 100.0, 2),
                "blended_multiplier_pct": round((float(row["blended_multiplier"]) - 1.0) * 100.0, 2),
                "stable_enough": "Ready" if bool(row["stable_enough"]) else "Advisory",
            }
            for row in result.mortality_basis.to_dict("records")
        ]
        if self.twin_v2_mortality_rows:
            latest_mortality = self.twin_v2_mortality_rows[-1]
            self.twin_v2_mortality_basis_version = str(latest_mortality["version_id"])
            self.twin_v2_mortality_credibility = float(latest_mortality["credibility_weight"])
            self.twin_v2_mortality_average_multiplier = float(latest_mortality["average_multiplier"])
            self.twin_v2_mortality_study_hash = str(latest_mortality["study_hash"])
            liability_change = 0.0
            if len(annual_rows) >= 2:
                liability_change = float(annual_rows[-1]["indexed_liability"] - annual_rows[0]["indexed_liability"])
            self.twin_v2_mortality_effect_text = (
                f"The active mortality basis is {self.twin_v2_mortality_basis_version}. "
                f"Credibility has reached {self.twin_v2_mortality_credibility:.1%}, so cohort mortality now runs about "
                f"{self.twin_v2_mortality_average_multiplier:.2f}x the Gompertz prior on average. "
                f"That changes liability timing and helps explain why indexed liabilities moved by {_compact_currency(liability_change)} over the run."
            )
            self.twin_v2_mortality_summary_rows = [
                {"label": "Baseline prior", "value": "Gompertz-Makeham prior"},
                {"label": "Basis version", "value": self.twin_v2_mortality_basis_version},
                {"label": "Credibility", "value": f"{self.twin_v2_mortality_credibility:.1%}"},
                {"label": "Average multiplier", "value": f"{self.twin_v2_mortality_average_multiplier:.2f}x baseline"},
                {"label": "Study hash", "value": self.twin_v2_mortality_study_hash[:18] + "…"},
            ]
        else:
            self.twin_v2_mortality_basis_version = ""
            self.twin_v2_mortality_credibility = 0.0
            self.twin_v2_mortality_average_multiplier = 1.0
            self.twin_v2_mortality_study_hash = ""
            self.twin_v2_mortality_effect_text = ""
            self.twin_v2_mortality_summary_rows = []

        classification_labels = {
            "advisory": "Advisory signal",
            "proposed": "Governance proposal",
            "executable": "Executable action",
        }
        self.twin_v2_investment_ballot_rows = [
            {
                "year": int(row["year"]),
                "round_name": str(row["round_name"]),
                "electorate_size": int(row["electorate_size"]),
                "total_window_contributions": _compact_currency(float(row["total_window_contributions"])),
                "winning_policy_name": str(row["winning_policy_name"]),
                "winning_support_pct": f"{float(row['winning_support_pct']):.1f}%",
                "status": str(row["status"]),
                "adopted_policy_name": str(row["adopted_policy_name"]),
                "blocked_reason": str(row["blocked_reason"]),
                "fallback_rule": str(row["fallback_rule"]),
            }
            for row in result.investment_ballots.to_dict("records")
        ]
        self.twin_v2_investment_policy_rows = [
            {
                "year": int(row["year"]),
                "policy_key": str(row["policy_key"]),
                "policy_name": str(row["policy_name"]),
                "status": str(row["status"]),
                "effective_year": int(row["effective_year"]),
                "reason": str(row["reason"]),
            }
            for row in result.investment_policy_history.to_dict("records")
        ]
        self.twin_v2_investment_vote_snapshot_rows = [
            {
                "year": int(row["year"]),
                "portfolio_name": str(row["portfolio_name"]),
                "weighted_votes": int(row["weighted_votes"]),
                "support_share_pct": f"{float(row['support_share_pct']):.2f}%",
                "voter_count": int(row["voter_count"]),
                "is_winner": str(row["is_winner"]),
                "guardrail_status": str(row["guardrail_status"]),
                "reason": str(row["reason"]),
            }
            for row in result.investment_vote_snapshot.to_dict("records")
        ]
        self.twin_v2_investment_effect_rows = [
            {
                "ballot_year": int(row["ballot_year"]),
                "winning_policy_name": str(row["winning_policy_name"]),
                "adopted_policy_name": str(row["adopted_policy_name"]),
                "status": str(row["status"]),
                "before_nav": f"£{float(row['before_nav_m']):.1f}m",
                "after_nav": f"£{float(row['after_nav_m']):.1f}m",
                "funded_ratio_change": f"{float(row['funded_ratio_change_pct']):+.1f} pts",
                "gini_change": f"{float(row['gini_change_pct']):+.1f} pts",
                "stress_pass_change": f"{float(row['stress_pass_change_pct']):+.1f} pts",
                "summary": str(row["summary"]),
            }
            for row in result.investment_effects.to_dict("records")
        ]
        self.twin_v2_investment_onchain_rows = [
            {
                "year": int(row["year"]),
                "simulation": str(row["simulation"]),
                "classification_label": classification_labels.get(str(row["classification"]), "Mapped action"),
                "contract_action": f"{row['contract']}.{row['action']}",
                "detail": str(row["detail"]),
            }
            for row in result.investment_onchain.to_dict("records")
        ]
        self.twin_v2_investment_summary_text = str(result.investment_summary.get("summary_text", ""))
        self.twin_v2_investment_ballot_count = int(result.investment_summary.get("ballot_count", 0))
        self.twin_v2_investment_adopted_count = int(result.investment_summary.get("adopted_count", 0))
        self.twin_v2_investment_blocked_count = int(result.investment_summary.get("blocked_count", 0))
        self.twin_v2_active_policy_name = str(result.investment_summary.get("latest_policy_name", ""))

        cohort_rows = [
            {
                "cohort": int(row["cohort"]),
                "members": int(row["members"]),
                "epv_contributions": float(row["epv_contributions"]),
                "epv_benefits": float(row["epv_benefits"]),
                "money_worth_ratio": float(row["money_worth_ratio"]),
                "year": int(row["year"]),
                "stress_load": float(row["stress_load"]),
                "per_member_epv": float(row["per_member_epv"]),
                "members_k": round(float(row["members"]) / 1_000, 2),
            }
            for row in result.cohort_metrics.to_dict("records")
        ]
        self.twin_v2_cohort_rows = cohort_rows
        if cohort_rows:
            latest_year = max(int(row["year"]) for row in cohort_rows)
            latest_rows = [row for row in cohort_rows if int(row["year"]) == latest_year]
            focus_keys = set(_sample_cohort_keys(latest_rows, limit=12))
            self.twin_v2_focus_cohort_rows = [
                row for row in latest_rows if int(row["cohort"]) in focus_keys
            ]
            if len(latest_rows) > len(self.twin_v2_focus_cohort_rows):
                self.twin_v2_cohort_focus_note = (
                    f"Showing {len(self.twin_v2_focus_cohort_rows)} representative cohorts for {latest_year} "
                    "to keep the chart readable."
                )
            else:
                self.twin_v2_cohort_focus_note = f"Showing all cohorts for {latest_year}."
        else:
            self.twin_v2_focus_cohort_rows = []
            self.twin_v2_cohort_focus_note = "No cohort view is available yet."

        self.twin_v2_event_rows = [
            {
                "year": int(row["year"]),
                "lane": str(row["lane"]),
                "label": str(row["label"]),
                "detail": str(row["detail"]),
                "severity": str(row["severity"]),
                "contract": str(row["contract"]),
                "action": str(row["action"]),
                "classification": str(row["classification"]),
                "contract_action": f"{row['contract']}.{row['action']}",
            }
            for row in result.events.to_dict("records")
        ]
        self.twin_v2_reserve_interventions = sum(
            1 for row in result.onchain.to_dict("records")
            if str(row.get("simulation", "")) == "Reserve released to honour pensions"
        )
        event_counts: dict[str, int] = {}
        for row in self.twin_v2_event_rows:
            event_counts[row["label"]] = event_counts.get(row["label"], 0) + 1
        self.twin_v2_event_mix_rows = [
            {"label": label, "count": count}
            for label, count in sorted(event_counts.items(), key=lambda item: (-item[1], item[0]))
        ]

        self.twin_v2_proposal_rows = [
            {
                "year": int(row["year"]),
                "proposal": str(row["proposal"]),
                "target_cohort": int(row["target_cohort"]),
                "before_mwr": float(row["before_mwr"]),
                "after_mwr": float(row["after_mwr"]),
                "passed": str(row["passed"]),
                "reason": str(row["reason"]),
                "contract": str(row["contract"]),
                "action": str(row["action"]),
                "classification": str(row["classification"]),
                "contract_action": f"{row['contract']}.{row['action']}",
            }
            for row in result.proposals.to_dict("records")
        ]

        self.twin_v2_onchain_rows = [
            {
                "year": int(row["year"]),
                "simulation": str(row["simulation"]),
                "contract": str(row["contract"]),
                "action": str(row["action"]),
                "classification": str(row["classification"]),
                "classification_label": classification_labels.get(str(row["classification"]), "Mapped action"),
                "detail": str(row["detail"]),
                "contract_action": f"{row['contract']}.{row['action']}",
            }
            for row in result.onchain.to_dict("records")
        ]
        response_lookup: dict[tuple[int, str], list[dict]] = {}
        for row in self.twin_v2_onchain_rows:
            response_lookup.setdefault((int(row["year"]), str(row["simulation"])), []).append(row)
        self.twin_v2_event_story_rows = []
        for row in self.twin_v2_event_rows:
            matching = response_lookup.get((int(row["year"]), str(row["label"])), [])
            if not matching and row["label"] == "Unfair reform proposal":
                matching = [
                    r for r in self.twin_v2_onchain_rows
                    if int(r["year"]) == int(row["year"]) and str(r["simulation"]) == "Governance proposal evaluated"
                ]
            response = (
                matching[0]["detail"]
                if matching
                else "The protocol recorded the event for monitoring rather than executing a direct contract action."
            )
            self.twin_v2_event_story_rows.append(
                {
                    "year": int(row["year"]),
                    "headline": str(row["label"]),
                    "what_happened": str(row["detail"]),
                    "why_it_matters": _event_importance_text(str(row["label"])),
                    "protocol_response": response,
                    "classification": str(row["classification"]),
                    "classification_label": classification_labels.get(str(row["classification"]), "Mapped action"),
                    "contract_action": str(row["contract_action"]),
                }
            )

        persona_rows = [
            {
                "year": int(row["year"]),
                "key": str(row["key"]),
                "label": str(row["label"]),
                "description": str(row["description"]),
                "age": int(row["age"]),
                "retirement_age": int(row["retirement_age"]),
                "status": str(row["status"]),
                "salary": float(row["salary"]),
                "balance": float(row["balance"]),
                "piu_balance": float(row["piu_balance"]),
                "piu_price": float(row["piu_price"]),
                "nominal_piu_value": float(row["nominal_piu_value"]),
                "benefit_piu": float(row["benefit_piu"]),
                "annual_benefit": float(row["annual_benefit"]),
                "contributions_paid": float(row["contributions_paid"]),
                "benefits_received": float(row["benefits_received"]),
                "balance_k": round(float(row["balance"]) / 1_000, 2),
                "piu_balance_k": round(float(row["piu_balance"]) / 1_000, 3),
                "nominal_piu_value_k": round(float(row["nominal_piu_value"]) / 1_000, 2),
                "salary_k": round(float(row["salary"]) / 1_000, 2),
                "annual_benefit_k": round(float(row["annual_benefit"]) / 1_000, 2),
            }
            for row in result.personas.to_dict("records")
        ]
        by_persona: dict[str, list[dict]] = {
            "young": [], "mid": [], "near": [], "retiree": [],
        }
        for row in persona_rows:
            if row["key"] in by_persona:
                by_persona[row["key"]].append(row)
        self.twin_v2_story_young_rows = by_persona["young"]
        self.twin_v2_story_mid_rows = by_persona["mid"]
        self.twin_v2_story_near_rows = by_persona["near"]
        self.twin_v2_story_retiree_rows = by_persona["retiree"]
        self.twin_v2_persona_catalog_rows = persona_catalog()

        story_summaries: list[dict] = []
        for persona in self.twin_v2_persona_catalog_rows:
            rows = by_persona.get(str(persona["key"]), [])
            if not rows:
                continue
            opening = rows[0]
            latest = rows[-1]
            retirement_point = next((row for row in rows if str(row["status"]) == "Retired"), None)
            death_point = next((row for row in rows if str(row["status"]) == "Deceased"), None)
            turning_point = (
                f"Retired in {retirement_point['year']} at age {retirement_point['age']}."
                if retirement_point
                else f"Died in {death_point['year']} at age {death_point['age']}."
                if death_point
                else "Stayed in accumulation throughout the run."
            )
            story_summaries.append(
                {
                    "key": str(persona["key"]),
                    "label": str(persona["label"]),
                    "description": str(persona["description"]),
                    "status": latest["status"],
                    "age": int(latest["age"]),
                    "start_age": int(opening["age"]),
                    "retirement_age": int(opening["retirement_age"]),
                    "retirement_year": int(retirement_point["year"]) if retirement_point else None,
                    "death_year": int(death_point["year"]) if death_point else None,
                    "balance": _compact_currency(float(latest["balance"])),
                    "piu_balance_display": _compact_number(float(latest["piu_balance"])),
                    "piu_value": _compact_currency(float(latest["nominal_piu_value"])),
                    "piu_price_display": f"£{float(latest['piu_price']):.3f}",
                    "benefit_piu_display": _compact_number(float(latest["benefit_piu"])),
                    "unit_position": (
                        _compact_number(float(latest["benefit_piu"]))
                        if latest["status"] == "Retired"
                        else _compact_number(float(latest["piu_balance"]))
                    ),
                    "unit_position_note": (
                        "Pension units now paying out"
                        if latest["status"] == "Retired"
                        else "No live units after death"
                        if latest["status"] == "Deceased"
                        else "Accumulated PIUs still being built up"
                    ),
                    "salary": _compact_currency(float(latest["salary"])),
                    "annual_benefit": _compact_currency(float(latest["annual_benefit"])),
                    "narrative": (
                        f"Started at age {opening['age']} and ends at age {latest['age']} as {latest['status'].lower()}."
                    ),
                    "turning_point": turning_point,
                }
            )
        self.twin_v2_story_summary_rows = story_summaries
        self._sync_twin_v2_story_selection()

        self.twin_v2_assumption_rows = [{"note": note} for note in result.assumptions]
        self.twin_v2_model_scope_rows = [
            {"scope": "Person level", "detail": result.person_level_note},
            {"scope": "Cohort level", "detail": result.cohort_level_note},
            {"scope": "Performance", "detail": result.performance_note},
        ]

        if annual_rows:
            final = annual_rows[-1]
            self.twin_v2_final_population = int(final["population_total"])
            self.twin_v2_final_active = int(final["active_count"])
            self.twin_v2_final_retired = int(final["retired_count"])
            self.twin_v2_final_deceased = int(final["deceased_count"])
            self.twin_v2_average_age = float(final["average_age"])
            self.twin_v2_average_salary = float(final["average_salary"])
            self.twin_v2_final_nav = float(final["fund_nav"])
            self.twin_v2_final_reserve = float(final["reserve"])
            self.twin_v2_final_funded_ratio = float(final["funded_ratio"])
            self.twin_v2_final_cpi_index = float(final["cpi_index"])
            self.twin_v2_final_piu_price = float(final["piu_price"])
            self.twin_v2_final_indexed_liability = float(final["indexed_liability"])
            self.twin_v2_final_pius_per_1000 = float(final["pius_per_1000"])
            self.twin_v2_final_accrued_pius = float(final["accrued_pius"])
            self.twin_v2_final_pension_units = float(final["pension_units"])
            self.twin_v2_average_gini = float(
                sum(float(row["gini"]) for row in annual_rows) / len(annual_rows)
            )
            self.twin_v2_average_stress_pass = float(
                sum(float(row["stress_pass_rate"]) for row in annual_rows) / len(annual_rows)
            )
        else:
            self.twin_v2_final_population = 0
            self.twin_v2_final_active = 0
            self.twin_v2_final_retired = 0
            self.twin_v2_final_deceased = 0
            self.twin_v2_average_age = 0.0
            self.twin_v2_average_salary = 0.0
            self.twin_v2_final_nav = 0.0
            self.twin_v2_final_reserve = 0.0
            self.twin_v2_final_funded_ratio = 0.0
            self.twin_v2_final_cpi_index = 0.0
            self.twin_v2_final_piu_price = 0.0
            self.twin_v2_final_indexed_liability = 0.0
            self.twin_v2_final_pius_per_1000 = 0.0
            self.twin_v2_final_accrued_pius = 0.0
            self.twin_v2_final_pension_units = 0.0
            self.twin_v2_average_gini = 0.0
            self.twin_v2_average_stress_pass = 0.0

        self.twin_v2_event_count = len(self.twin_v2_event_rows)
        self.twin_v2_proposal_count = len(self.twin_v2_proposal_rows)
        self.twin_v2_performance_note = result.performance_note
        self.twin_v2_person_level_note = result.person_level_note
        self.twin_v2_cohort_level_note = result.cohort_level_note
        self.twin_v2_ran = True
        self._refresh_twin_v2_gas()
        self._build_twin_v2_run_summary()

        _event_log().append(
            "twin_v2_simulation_run",
            baseline=self.twin_v2_baseline_key,
            years=int(self.twin_v2_horizon_years),
            members=int(self.twin_v2_population_size),
            events=int(self.twin_v2_event_count),
            proposals=int(self.twin_v2_proposal_count),
        )
        self._refresh_events()

    # ======================================================================
    # Wallet / on-chain handlers (browser bridge — MetaMask + ethers.js)
    # ======================================================================
    # The Reflex server never holds a private key. These handlers run the
    # browser-side bridge (see assets/wallet_bridge.js) via rx.call_script
    # and receive results through dedicated callbacks below. Nothing here
    # signs transactions directly.

    # ---- JS bridge plumbing ------------------------------------------------
    # The wallet bridge source is injected into head_components as an
    # inline script so the first wallet click does not depend on a
    # separate asset request succeeding.
    # Script-load order is not guaranteed to finish before the user clicks
    # "Connect wallet" on a fast page, so every call_script here is wrapped
    # in a small retry IIFE that waits up to ~2s for window.aequitasWallet
    # to appear before giving up. Without this, the first click on a cold
    # page silently resolves to `undefined` and no MetaMask popup fires.
    _BRIDGE_RETRY_WAIT = (
        "(async () => {"
        "  for (let i = 0; i < 40; i++) {"
        "    if (window.aequitasWallet) return true;"
        "    await new Promise(r => setTimeout(r, 50));"
        "  }"
        "  return false;"
        "})()"
    )

    @staticmethod
    def _bridge_call(body: str) -> str:
        """Return a JS expression that waits for window.aequitasWallet
        to exist (up to ~2 s) and then invokes `body`. `body` must be a
        Promise-returning expression like `window.aequitasWallet.connect()`.
        Resolves to the inner body's result, or a falsy error envelope
        if the bridge never loads.
        """
        return (
            "(async () => {"
            "  for (let i = 0; i < 40; i++) {"
            "    if (window.aequitasWallet) {"
            f"      return await ({body});"
            "    }"
            "    await new Promise(r => setTimeout(r, 50));"
            "  }"
            "  return { ok: false, error: 'wallet bridge failed to load' };"
            "})()"
        )

    def connect_wallet(self):
        """Trigger MetaMask connection in the browser. Result flows back
        through `on_wallet_connected`."""
        self.wallet_last_error = ""
        self.wallet_status_message = "Opening MetaMask…"
        return rx.call_script(
            self._bridge_call("window.aequitasWallet.connect()"),
            callback=AppState.on_wallet_connected,
        )

    def on_wallet_connected(self, result: Any):
        """Callback invoked by rx.call_script when connect() resolves.

        `result` shape (from the JS bridge):
          { ok: bool, address?: str, chainId?: int, error?: str }
        """
        r = result or {}
        if isinstance(r, str):
            # Some Reflex versions stringify — try to parse JSON loosely.
            try:
                import json as _json
                r = _json.loads(r)
            except Exception:
                r = {"ok": False, "error": r}
        if not isinstance(r, dict):
            r = {"ok": False, "error": "Unexpected wallet response"}

        if r.get("ok"):
            addr = str(r.get("address") or "").lower()
            cid  = int(r.get("chainId") or 0)
            self.wallet_connected  = True
            self.wallet_address    = addr
            self.wallet_short      = short_address(addr)
            self.wallet_chain_id   = cid
            self.wallet_chain_name = _chain_name(cid)
            self.wallet_is_sepolia = _is_sepolia(cid)
            self.wallet_status_message = (
                "Connected to Sepolia" if self.wallet_is_sepolia
                else f"Connected · wrong network ({self.wallet_chain_name})"
            )
            self.wallet_last_error = ""
            _event_log().append(
                "wallet_connected",
                address=addr,
                chain_id=cid,
                chain_name=self.wallet_chain_name,
            )
            self._refresh_investment_governance()
        else:
            self.wallet_connected = False
            self.wallet_last_error = str(r.get("error") or "Connection cancelled")
            self.wallet_status_message = "Wallet not connected"
            self._refresh_investment_governance()

    def switch_to_sepolia(self):
        """Ask MetaMask to switch the active network to Sepolia."""
        self.wallet_status_message = "Switching network…"
        return rx.call_script(
            self._bridge_call("window.aequitasWallet.switchToSepolia()"),
            callback=AppState.on_chain_changed,
        )

    def refresh_wallet_state(self):
        """Poll the JS bridge for the latest cached wallet state.

        Invoked by a small JS listener on `/actions` whenever MetaMask
        emits `chainChanged` or `accountsChanged`, so the navbar badge
        and status banner stay live without a page reload.
        """
        return rx.call_script(
            self._bridge_call("window.aequitasWallet.getState()"),
            callback=AppState.on_wallet_state_snapshot,
        )

    def refresh_tx_confirmation(self):
        """Poll the browser bridge for the latest confirmed tx hash."""
        return rx.call_script(
            "window.__aequitasLastConfirmedTxReceipt || { hash: window.__aequitasLastConfirmedTx || '' }",
            callback=AppState.on_tx_confirmed,
        )

    def on_wallet_state_snapshot(self, result: Any):
        """Apply a snapshot from `window.aequitasWallet.getState()`.

        The snapshot is a plain object (see wallet_bridge.js::STATE):
          { ok, connected, address, chainId, providerName, error }
        """
        r = result or {}
        if isinstance(r, str):
            try:
                import json as _json
                r = _json.loads(r)
            except Exception:
                r = {}
        if not isinstance(r, dict):
            return
        if not r.get("connected"):
            # Account was disconnected in MetaMask — mirror that locally.
            if self.wallet_connected:
                self.wallet_connected = False
                self.wallet_address = ""
                self.wallet_short = ""
                self.wallet_chain_id = 0
                self.wallet_chain_name = ""
                self.wallet_is_sepolia = False
                self.wallet_status_message = "Wallet disconnected"
            return
        addr = str(r.get("address") or "").lower()
        cid = int(r.get("chainId") or 0)
        changed = (
            addr != self.wallet_address
            or cid != self.wallet_chain_id
            or not self.wallet_connected
        )
        if not changed:
            return
        self.wallet_connected  = True
        self.wallet_address    = addr
        self.wallet_short      = short_address(addr)
        self.wallet_chain_id   = cid
        self.wallet_chain_name = _chain_name(cid)
        self.wallet_is_sepolia = _is_sepolia(cid)
        self.wallet_status_message = (
            "Connected to Sepolia" if self.wallet_is_sepolia
            else f"Connected · wrong network ({self.wallet_chain_name})"
        )
        self.wallet_last_error = ""
        self._refresh_investment_governance()

    def on_chain_changed(self, result: Any):
        r = result or {}
        if isinstance(r, dict) and r.get("ok"):
            cid = int(r.get("chainId") or 0)
            self.wallet_chain_id   = cid
            self.wallet_chain_name = _chain_name(cid)
            self.wallet_is_sepolia = _is_sepolia(cid)
            self.wallet_status_message = (
                "Connected to Sepolia" if self.wallet_is_sepolia
                else f"Connected · wrong network ({self.wallet_chain_name})"
            )
        else:
            err = (r.get("error") if isinstance(r, dict) else None) or "Switch cancelled"
            self.wallet_last_error = str(err)

    def on_tx_confirmed(self, result: Any):
        """Mark the currently tracked transaction as confirmed."""
        payload = result or {}
        if isinstance(payload, str):
            txh = str(payload).strip().lower()
            payload = {"hash": txh}
        elif isinstance(payload, dict):
            txh = str(payload.get("hash") or "").strip().lower()
        else:
            txh = str(payload).strip().lower()
            payload = {"hash": txh}
        if not txh or txh != (self.last_tx_hash or "").lower():
            return
        if self.last_tx_status == "confirmed":
            return
        self.last_tx_status = "confirmed"
        self.last_tx_error = ""
        fee_wei = str(payload.get("feeWei") or payload.get("fee_wei") or "")
        gas_used = int(payload.get("gasUsed") or payload.get("gas_used") or 0)
        self.last_tx_fee_wei = fee_wei
        self.last_tx_gas_used = gas_used
        self.last_tx_fee_eth = fee_eth_from_wei(fee_wei) if fee_wei else 0.0
        self.last_tx_fee_gbp = fee_gbp_from_wei(fee_wei, self.gas_network_preset) if fee_wei else 0.0
        _event_log().append(
            "tx_confirmed",
            action=self.last_tx_action_key,
            label=self.last_tx_action,
            hash=txh,
            status=self.last_tx_status,
            gas_used=gas_used,
            fee_wei=fee_wei,
        )
        self._refresh_events()
        self._refresh_actual_fee_rows()
        self._refresh_investment_governance()

    def disconnect_wallet(self):
        """Local-only disconnect — MetaMask has no revoke API."""
        self.wallet_connected = False
        self.wallet_address = ""
        self.wallet_short = ""
        self.wallet_chain_id = 0
        self.wallet_chain_name = ""
        self.wallet_is_sepolia = False
        self.wallet_status_message = "Wallet not connected"
        self._refresh_investment_governance()

    # ----- confirmation drawer --------------------------------------------
    # Action keys understood by the Operator Action Center. Keep this
    # table small and human-readable — the confirm drawer reads from it.
    # ClassVar so Reflex does not mistake this constant for a state field.
    _ACTIONS: ClassVar[dict[str, dict]] = {
        "demo_flow": {
            "label":      "Run end-to-end demo flow",
            "contract":   "Scripted",
            "function":   "DemoFlow.s.sol",
            "summary":    "Run the scripted end-to-end walkthrough against the "
                          "current deployment: register, contribute, propose, "
                          "stress, and settle.",
            "actuarial":  "Replays the canonical Aequitas lifecycle so a juror "
                          "can watch every primitive fire in order.",
            "protocol":   "Nothing new is computed — the script re-emits a "
                          "canonical sequence of transactions.",
            "mode":       "Off-chain",
            "reversible": "No — each transaction is final once included in a block.",
            "live":       False,
        },
        "publish_baseline": {
            "label":      "Publish cohort baseline",
            "contract":   "FairnessGate",
            "function":   "setBaseline",
            "summary":    "Snapshot the current per-cohort Money-Worth Ratio "
                          "so future proposals can be evaluated against it.",
            "actuarial":  "Locks the baseline MWRᵢ vector used by the fairness "
                          "corridor test.",
            "protocol":   "Without a baseline, FairnessGate cannot evaluate "
                          "proposals — this must run before the first vote.",
            "mode":       "Live on Sepolia",
            "reversible": "Replacing a baseline overwrites the stored vector; "
                          "history is preserved in event logs.",
            "live":       True,
        },
        "publish_piu_price": {
            "label":      "Publish CPI-linked PIU price",
            "contract":   "CohortLedger",
            "function":   "setPiuPrice",
            "summary":    "Publish the current CPI-linked PIU price so the on-chain ledger uses the same inflation indexation as the actuarial engine.",
            "actuarial":  "PIU is the pension unit of account: when CPI rises, each nominal contribution buys fewer PIUs and each existing PIU represents a larger nominal pension claim.",
            "protocol":   "Updates CohortLedger's live PIU price so contribution minting and retirement conversion remain aligned with the indexed accounting rule.",
            "mode":       "Live on Sepolia",
            "reversible": "A later CPI reading can publish a new price, but each published price remains visible in the event log.",
            "live":       True,
        },
        "publish_mortality_basis": {
            "label":      "Publish mortality basis snapshot",
            "contract":   "MortalityBasisOracle",
            "function":   "publishBasis",
            "summary":    "Publish the active cohort-level mortality basis snapshot so future valuations and governance actions can prove which mortality assumption set was in force.",
            "actuarial":  "Starts from the Gompertz prior, then blends toward observed fund experience using a credibility weight rather than switching abruptly.",
            "protocol":   "Only the version id, cohort multiplier digest, credibility score, effective date, and study hash go on chain. Raw death records and private member data stay off chain.",
            "mode":       "Live on Sepolia",
            "reversible": "A new snapshot can supersede the active basis, but the old version remains in the immutable assumption history.",
            "live":       True,
        },
        "publish_actuarial_method": {
            "label":      "Publish actuarial method version",
            "contract":   "ActuarialMethodRegistry",
            "function":   "registerMethod",
            "summary":    "Publish the current actuarial methodology version so the chain can prove which formula family and parameter schema governed later results.",
            "actuarial":  "This does not move the full engine on-chain. It timestamps the method family, spec hash, reference implementation hash, and schema version that the Python engine used.",
            "protocol":   "Creates an immutable methodology record for audit. This is how the protocol prevents silent retroactive rewriting of the actuarial method after a valuation is published.",
            "mode":       "Live on Sepolia",
            "reversible": "A newer method version can supersede the active one, but the old version remains in the history.",
            "live":       True,
        },
        "publish_valuation_snapshot": {
            "label":      "Publish valuation snapshot",
            "contract":   "ActuarialResultRegistry",
            "function":   "publishValuationSnapshot",
            "summary":    "Publish the parameter set and input commitments for the current valuation so later results can prove exactly which assumptions and snapshot governed them.",
            "actuarial":  "The Python engine computes the valuation in full; the chain stores only compact commitments such as the parameter-set hash, member snapshot hash, and cohort-summary hash.",
            "protocol":   "This creates the immutable input side of the actuarial proof layer without exposing private member records on-chain.",
            "mode":       "Live on Sepolia",
            "reversible": "No — snapshots are append-only audit records.",
            "live":       True,
        },
        "publish_actuarial_result_bundle": {
            "label":      "Publish actuarial result bundle",
            "contract":   "ActuarialResultRegistry",
            "function":   "publishResultBundle",
            "summary":    "Publish the scheme-level actuarial result commitment tied back to the declared method versions, parameter snapshot, and input commitment.",
            "actuarial":  "This publishes compact summary metrics and the hash of the full off-chain result bundle. It does not attempt to re-run the full pension engine on-chain.",
            "protocol":   "Creates the immutable provenance chain from method version to parameter snapshot to valuation input to published result bundle.",
            "mode":       "Live on Sepolia",
            "reversible": "No — result bundles are append-only publications.",
            "live":       True,
        },
        "submit_proposal": {
            "label":      "Submit governance proposal",
            "contract":   "FairnessGate",
            "function":   "submitAndEvaluate",
            "summary":    "Send a reform proposal on-chain. The contract re-"
                          "computes the fairness corridor and emits PASS/FAIL.",
            "actuarial":  "Checks max_{i,j}|ΔMWRᵢ − ΔMWRⱼ| / parity ≤ δ against "
                          "the stored baseline.",
            "protocol":   "Publishes the governance verdict irrevocably to the "
                          "audit chain.",
            "mode":       "Live on Sepolia",
            "reversible": "No — the verdict is written to the event log.",
            "live":       True,
        },
        "create_investment_ballot": {
            "label":      "Create investment ballot",
            "contract":   "InvestmentPolicyBallot",
            "function":   "createBallot",
            "summary":    "Open a named member ballot for the predefined model portfolios. The chain records the portfolio ids and allocation hashes, not arbitrary trading instructions.",
            "actuarial":  "Members vote with one base vote plus a capped concave boost from current-window contributions. The weighting rule uses the current decision-period snapshot, not lifetime wealth.",
            "protocol":   "Creates the ballot round on-chain so every later vote and final winner can be audited without turning pension governance into a tokenized plutocracy.",
            "mode":       "Live on Sepolia",
            "reversible": "No — ballot creation becomes part of the governance audit trail.",
            "live":       True,
        },
        "publish_investment_weights": {
            "label":      "Publish investment weight snapshot",
            "contract":   "InvestmentPolicyBallot",
            "function":   "setBallotWeights",
            "summary":    "Publish the current decision-window voting snapshot so the ballot uses capped concave weights rather than raw wealth or token balances.",
            "actuarial":  "The Python engine computes the current-window contribution measure, applies the 1 + sqrt(normalized contribution) rule, and caps every published member share at 5%.",
            "protocol":   "Stores only the compact voter weight snapshot the ballot needs. The chain does not infer contribution windows on its own.",
            "mode":       "Live on Sepolia",
            "reversible": "No — the weight snapshot is part of the ballot audit record.",
            "live":       True,
        },
        "finalize_investment_ballot": {
            "label":      "Finalize investment ballot",
            "contract":   "InvestmentPolicyBallot",
            "function":   "finalizeBallot",
            "summary":    "Close the ballot and publish the winning model portfolio, but only if the Python guardrail validator says the winner is acceptable for funding, fairness, and stress.",
            "actuarial":  "This is the final off-chain economic gate: the ballot winner must still pass funded-ratio, fairness-dispersion, and stress-pass guardrails before publication.",
            "protocol":   "Publishes the adopted investment-policy hash on-chain. It does not place trades or instruct an asset custodian.",
            "mode":       "Live on Sepolia",
            "reversible": "No — the published winner becomes the visible on-chain policy decision for that ballot round.",
            "live":       True,
        },
        "cast_investment_vote": {
            "label":      "Cast investment ballot vote",
            "contract":   "InvestmentPolicyBallot",
            "function":   "castVote",
            "summary":    "Cast one member vote for one predefined model portfolio inside the current ballot window.",
            "actuarial":  "Your weight is taken from the already-published current-window snapshot, so the chain never needs private salary history or lifetime wealth.",
            "protocol":   "Records one wallet-level vote for one model portfolio id. The chain stores the choice and tally, not private member economics.",
            "mode":       "Live on Sepolia",
            "reversible": "No — one wallet, one vote per ballot.",
            "live":       True,
        },
        "publish_stress": {
            "label":      "Publish fairness stress result",
            "contract":   "StressOracle",
            "function":   "updateStressLevel",
            "summary":    "Publish the latest Monte Carlo corridor-breach "
                          "probability to the on-chain stress oracle.",
            "actuarial":  "Records the p95 stressed Gini / corridor-breach rate "
                          "so on-chain consumers can gate new proposals.",
            "protocol":   "Downstream contracts (e.g. BackstopVault) read from "
                          "StressOracle to arm themselves ahead of a shock.",
            "mode":       "Live on Sepolia",
            "reversible": "No — each published level is a permanent oracle update.",
            "live":       True,
        },
        "fund_reserve": {
            "label":      "Fund the reserve vault",
            "contract":   "BackstopVault",
            "function":   "deposit",
            "summary":    "Top up the protocol's reserve vault so it can cover "
                          "a future shortfall.",
            "actuarial":  "Increases the capital buffer sized against the tail "
                          "of the corridor stress distribution.",
            "protocol":   "Funds sit in BackstopVault and are only released when "
                          "a shortfall triggers governance.",
            "mode":       "Live on Sepolia",
            "reversible": "Funds are governance-withdrawable; the deposit itself "
                          "is recorded permanently.",
            "live":       True,
        },
        "release_reserve": {
            "label":      "Release reserve to cover shortfall",
            "contract":   "BackstopVault",
            "function":   "release",
            "summary":    "Draw down the reserve to fill a liability shortfall "
                          "surfaced by this period's valuation.",
            "actuarial":  "Transfers capital into LongevaPool equal to the "
                          "present-value gap published by the Python engine.",
            "protocol":   "Requires guardian role; event emitted for audit.",
            "mode":       "Live on Sepolia",
            "reversible": "No — the transfer is on-chain.",
            "live":       True,
        },
        "open_retirement": {
            "label":      "Open member retirement",
            "contract":   "VestaRouter",
            "function":   "openRetirement",
            "summary":    "Transition a member from accumulation to decumulation "
                          "with a sustainable annual benefit.",
            "actuarial":  "Locks an EPV-anchored benefit using the live mortality "
                          "curve — longevity risk moves to the pool.",
            "protocol":   "Creates a BenefitStreamer flow and flags the member "
                          "as retired in CohortLedger.",
            "mode":       "Live on Sepolia",
            "reversible": "The flow can be paused by governance but not unlocked.",
            "live":       True,
        },
        "deploy_protocol": {
            "label":      "Deploy protocol to Sepolia",
            "contract":   "Foundry",
            "function":   "forge script Deploy.s.sol",
            "summary":    "Run the one-shot deploy script that wires all eight "
                          "contracts and assigns the protocol roles.",
            "actuarial":  "No actuarial logic runs on-chain at deploy — this "
                          "only instantiates the execution surface.",
            "protocol":   "After success, paste addresses into "
                          "contracts/deployments/sepolia.json to connect the UI.",
            "mode":       "Off-chain",
            "reversible": "Redeployment produces new addresses; old instances "
                          "remain on-chain.",
            "live":       False,
        },
    }

    _SANDBOX_STEPS: ClassVar[list[dict[str, Any]]] = [
        {
            "key": "demo_members",
            "title": "Seed demo members",
            "contract": "CohortLedger",
            "function": "registerMember",
            "kind": "offchain",
            "summary": "Load the deterministic sandbox membership set so the protocol has named people and cohorts to reason about.",
        },
        {
            "key": "demo_contributions",
            "title": "Record demo contributions",
            "contract": "CohortLedger",
            "function": "contribute",
            "kind": "offchain",
            "summary": "Populate the deterministic contribution history that drives the sandbox valuation and cohort fairness state.",
        },
        {
            "key": "publish_piu_price",
            "title": "Publish CPI-linked PIU price",
            "contract": "CohortLedger",
            "function": "setPiuPrice",
            "kind": "action",
            "summary": "Publish the CPI-linked PIU price so the on-chain ledger uses the same indexed pension unit as the engine.",
        },
        {
            "key": "publish_mortality_basis",
            "title": "Publish mortality basis snapshot",
            "contract": "MortalityBasisOracle",
            "function": "publishBasis",
            "kind": "action",
            "summary": "Publish the versioned mortality basis snapshot that blends the baseline prior with observed fund experience.",
        },
        {
            "key": "publish_actuarial_method",
            "title": "Publish actuarial method version",
            "contract": "ActuarialMethodRegistry",
            "function": "registerMethod",
            "kind": "action",
            "summary": "Publish the actuarial method family, version, and spec hashes that govern the current proof layer.",
        },
        {
            "key": "publish_valuation_snapshot",
            "title": "Publish valuation snapshot",
            "contract": "ActuarialResultRegistry",
            "function": "publishValuationSnapshot",
            "kind": "action",
            "summary": "Publish the parameter snapshot and input commitments for the current valuation.",
        },
        {
            "key": "publish_actuarial_result_bundle",
            "title": "Publish actuarial result bundle",
            "contract": "ActuarialResultRegistry",
            "function": "publishResultBundle",
            "kind": "action",
            "summary": "Publish the compact result bundle that links the current result back to declared methods, parameters, and input commitments.",
        },
        {
            "key": "publish_baseline",
            "title": "Publish fairness baseline",
            "contract": "FairnessGate",
            "function": "setBaseline",
            "kind": "action",
            "summary": "Publish the baseline cohort fairness state so future proposals can be judged on-chain.",
        },
        {
            "key": "submit_proposal",
            "title": "Submit governance proposal",
            "contract": "FairnessGate",
            "function": "submitAndEvaluate",
            "kind": "action",
            "summary": "Send a deterministic sandbox proposal to the fairness gate and receive a pass/fail verdict.",
        },
        {
            "key": "publish_stress",
            "title": "Publish stress result",
            "contract": "StressOracle",
            "function": "updateStressLevel",
            "kind": "action",
            "summary": "Publish the latest stress outcome so the protocol can react before a shortfall becomes real.",
        },
        {
            "key": "fund_reserve",
            "title": "Fund reserve vault",
            "contract": "BackstopVault",
            "function": "deposit",
            "kind": "action",
            "summary": "Top up the reserve buffer that protects benefits during stress.",
        },
        {
            "key": "release_reserve",
            "title": "Release reserve",
            "contract": "BackstopVault",
            "function": "release",
            "kind": "action",
            "summary": "Release reserve capital into the scheme when the sandbox shows a shortfall.",
        },
        {
            "key": "open_retirement",
            "title": "Open retirement flow",
            "contract": "VestaRouter",
            "function": "openRetirement",
            "kind": "action",
            "summary": "Move a sample sandbox member into retirement and open the benefit flow.",
        },
    ]

    def open_action(self, action_key: str):
        """Open the confirmation drawer for one of the Action Center cards."""
        spec = self._ACTIONS.get(action_key)
        if not spec:
            return
        self.confirm_open         = True
        self.confirm_action_key   = action_key
        self.confirm_action_label = spec["label"]
        self.confirm_contract     = spec["contract"]
        self.confirm_function     = spec["function"]
        self.confirm_summary      = spec["summary"]
        self.confirm_actuarial    = spec["actuarial"]
        self.confirm_protocol     = spec["protocol"]
        self.confirm_reversible   = spec["reversible"]
        self.confirm_is_live      = bool(spec.get("live"))
        self.confirm_mode_label   = spec["mode"]
        self.confirm_target_addr  = ""
        self.confirm_call_args_json = ""
        self.confirm_call_value_wei = ""
        self.confirm_advanced_json = ""
        # Look up the target address from the on-chain registry if available.
        for row in self.registry_rows:
            if row.get("name") == spec["contract"]:
                self.confirm_target_addr = row.get("address", "")
                break
        # Minimal params preview — extended per-action if needed.
        self.confirm_params_rows = [
            {"key": "Target contract", "value": spec["contract"]},
            {"key": "Function",        "value": spec["function"]},
            {"key": "Mode",            "value": spec["mode"]},
        ]
        if self.confirm_action_key in {
            "publish_baseline",
            "publish_piu_price",
            "publish_mortality_basis",
            "publish_actuarial_method",
            "publish_valuation_snapshot",
            "publish_actuarial_result_bundle",
            "submit_proposal",
            "publish_stress",
            "fund_reserve",
            "release_reserve",
            "open_retirement",
        }:
            cohort_count = max(1, self.cohorts_count or len({int(row["cohort"]) for row in self.twin_v2_cohort_rows}) or 1)
            estimated_gas = gas_units_for_action(
                "register_member" if self.confirm_action_key == "demo_members" else
                "record_contribution" if self.confirm_action_key == "demo_contributions" else
                self.confirm_action_key,
                cohort_count=cohort_count,
            )
            self.confirm_params_rows.extend(
                [
                    {"key": "Estimated gas", "value": f"{estimated_gas:,} gas"},
                    {"key": "Estimated cost", "value": _compact_currency(fee_gbp_from_gas(estimated_gas, self.gas_network_preset))},
                    {"key": "Fee preset", "value": next((row["label"] for row in self.gas_network_rows if row["key"] == self.gas_network_preset), self.gas_network_preset)},
                ]
            )
        if self.confirm_target_addr:
            self.confirm_params_rows.append(
                {"key": "Deployed at", "value": self.confirm_target_addr}
            )
        elif spec.get("live") and spec["contract"] != "Scripted":
            self.confirm_is_live = False
            self.confirm_mode_label = "After next Sepolia deployment"
            self.confirm_params_rows.append(
                {"key": "Deployment status", "value": f"{spec['contract']} is not in the current deployment registry"}
            )
        if action_key == "publish_mortality_basis" and not self.confirm_target_addr:
            self.confirm_is_live = False
            self.confirm_mode_label = "After next Sepolia deployment"
            self.confirm_params_rows.append(
                {"key": "Deployment status", "value": "Contract not yet on the current Sepolia registry"}
            )
        if action_key == "publish_piu_price":
            call = encode_piu_price_update(
                _ledger().piu_price,
                cpi_level=_ledger().current_cpi,
            )
            self.confirm_call_args_json = json.dumps([str(arg) for arg in call.args])
            self.confirm_params_rows.extend(
                [
                    {"key": "Current CPI", "value": f"{_ledger().current_cpi:.3f}"},
                    {"key": "PIU price", "value": f"{_ledger().piu_price:.6f}"},
                    {"key": "Indexed rule", "value": "PIU price follows CPI explicitly"},
                ]
            )
            self.confirm_advanced_json = json.dumps(call.as_dict(), default=str)
        elif action_key == "publish_mortality_basis":
            snapshot = deterministic_sandbox_snapshot(
                members=_ledger().get_all_members(),
                valuation_year=int(self.valuation_year),
            )
            call = encode_mortality_basis_publish(snapshot)
            self.confirm_call_args_json = json.dumps([str(arg) for arg in call.args])
            self.confirm_params_rows.extend(
                [
                    {"key": "Basis version", "value": snapshot.version_id},
                    {"key": "Credibility", "value": f"{snapshot.credibility_weight:.1%}"},
                    {"key": "Study hash", "value": snapshot.study_hash[:18] + "…"},
                    {"key": "Privacy boundary", "value": "Cohort digest + proof hash only"},
                ]
            )
            self.confirm_advanced_json = json.dumps(call.as_dict(), default=str)
        elif action_key == "publish_actuarial_method":
            method_call = self.actuarial_method_payload or {}
            self.confirm_call_args_json = json.dumps(
                [str(arg) if not isinstance(arg, bool) else arg for arg in method_call.get("args", [])],
                default=str,
            )
            self.confirm_params_rows.extend(
                [
                    {"key": "Method family", "value": self.actuarial_method_rows[0]["family"] if self.actuarial_method_rows else "EPV"},
                    {"key": "Version", "value": self.actuarial_method_rows[0]["version"] if self.actuarial_method_rows else "epv_discrete_v1"},
                    {"key": "What the chain stores", "value": "Spec hash, reference implementation hash, schema hash, and effective date"},
                    {"key": "What stays off-chain", "value": "The full actuarial engine and private member data"},
                ]
            )
            self.confirm_advanced_json = json.dumps(method_call, default=str)
        elif action_key == "publish_valuation_snapshot":
            self.confirm_call_args_json = json.dumps(
                [str(arg) for arg in self.actuarial_valuation_payload.get("args", [])],
                default=str,
            )
            self.confirm_params_rows.extend(
                [
                    {"key": "Parameter set hash", "value": self.actuarial_parameter_rows[7]["value"] if len(self.actuarial_parameter_rows) > 7 else "—"},
                    {"key": "Member snapshot hash", "value": self.actuarial_parameter_rows[8]["value"] if len(self.actuarial_parameter_rows) > 8 else "—"},
                    {"key": "Cohort summary hash", "value": self.actuarial_parameter_rows[9]["value"] if len(self.actuarial_parameter_rows) > 9 else "—"},
                    {"key": "Privacy boundary", "value": "Hashes and compact counts only — no raw member records on-chain"},
                ]
            )
            self.confirm_advanced_json = json.dumps(self.actuarial_valuation_payload, default=str)
        elif action_key == "publish_actuarial_result_bundle":
            self.confirm_call_args_json = json.dumps(
                [str(arg) for arg in self.actuarial_result_payload.get("args", [])],
                default=str,
            )
            self.confirm_params_rows.extend(
                [
                    {"key": "Scheme MWR", "value": self.actuarial_result_rows[2]["value"] if len(self.actuarial_result_rows) > 2 else "—"},
                    {"key": "Funded ratio", "value": self.actuarial_result_rows[3]["value"] if len(self.actuarial_result_rows) > 3 else "—"},
                    {"key": "Result bundle hash", "value": self.actuarial_result_rows[5]["value"] if len(self.actuarial_result_rows) > 5 else "—"},
                    {"key": "Verifier posture", "value": "The chain stores the commitment and can spot-check selected claims"},
                ]
            )
            self.confirm_advanced_json = json.dumps(self.actuarial_result_payload, default=str)
        elif action_key == "create_investment_ballot":
            if not self.investment_policy_rows:
                self.confirm_is_live = False
                self.confirm_mode_label = "Load the sandbox electorate first"
                self.confirm_params_rows.append(
                    {"key": "Prerequisite", "value": "Load the deterministic member roster before opening a ballot"}
                )
                return
            call = encode_create_investment_ballot(
                build_ballot_draft(
                    _ledger(),
                    round_name=self.investment_round_name,
                    opens_at=self.investment_ballot_opens_at,
                    closes_at=self.investment_ballot_closes_at,
                )
            )
            self.confirm_call_args_json = json.dumps(
                [arg if not isinstance(arg, list) else [str(item) for item in arg] for arg in call.args],
                default=str,
            )
            self.confirm_params_rows.extend(
                [
                    {"key": "Ballot round", "value": self.investment_round_name},
                    {"key": "Model portfolios", "value": str(len(self.investment_policy_rows))},
                    {"key": "Voting rule", "value": "Base vote + capped concave boost"},
                    {"key": "Weight cap", "value": f"{MAX_EFFECTIVE_SHARE:.0%} max share per member"},
                ]
            )
            self.confirm_advanced_json = json.dumps(call.as_dict(), default=str)
        elif action_key == "publish_investment_weights":
            if not self.investment_weight_rows:
                self.confirm_is_live = False
                self.confirm_mode_label = "Load the sandbox electorate first"
                self.confirm_params_rows.append(
                    {"key": "Prerequisite", "value": "Build a ballot snapshot before publishing weights"}
                )
                return
            call = encode_investment_ballot_weights(
                self.investment_ballot_id,
                {
                    str(row["wallet"]): int(row["published_weight"])
                    for row in self.investment_weight_rows
                },
            )
            self.confirm_call_args_json = json.dumps(
                [
                    int(call.args[0]),
                    [str(arg) for arg in call.args[1]],
                    [int(arg) for arg in call.args[2]],
                ],
                default=str,
            )
            self.confirm_params_rows.extend(
                [
                    {"key": "Ballot id", "value": str(self.investment_ballot_id)},
                    {"key": "Eligible members", "value": str(len(self.investment_weight_rows))},
                    {"key": "Snapshot note", "value": self.investment_snapshot_note},
                    {"key": "Minimum voter count", "value": f"{MIN_VOTERS_FOR_STRICT_CAP} members for a strict 5% cap"},
                ]
            )
            self.confirm_advanced_json = json.dumps(call.as_dict(), default=str)
        elif action_key == "finalize_investment_ballot":
            if not self.investment_policy_rows:
                self.confirm_is_live = False
                self.confirm_mode_label = "Load the sandbox electorate first"
                self.confirm_params_rows.append(
                    {"key": "Prerequisite", "value": "Build a ballot draft before finalizing a winner"}
                )
                return
            call = encode_finalize_investment_ballot(self.investment_ballot_id)
            self.confirm_call_args_json = json.dumps([int(arg) for arg in call.args], default=str)
            self.confirm_params_rows.extend(
                [
                    {"key": "Ballot id", "value": str(self.investment_ballot_id)},
                    {"key": "Indicative winner", "value": self.investment_winner_name or "No winner yet"},
                    {"key": "Validation verdict", "value": "Passes guardrails" if self.investment_winner_passes else "Blocked by guardrails"},
                    {"key": "Guardrail note", "value": self.investment_winner_reason or "No validation result yet"},
                ]
            )
            if not self.investment_winner_passes:
                self.confirm_is_live = False
                self.confirm_mode_label = "Blocked by Python guardrails"
            self.confirm_advanced_json = json.dumps(call.as_dict(), default=str)

    def close_action(self):
        self.confirm_open = False

    def open_investment_vote_action(self, portfolio_key: str):
        portfolio_key = str(portfolio_key)
        policy_row = next(
            (row for row in self.investment_policy_rows if str(row["key"]) == portfolio_key),
            None,
        )
        if policy_row is None:
            return
        self.open_action("cast_investment_vote")
        call = encode_investment_vote(self.investment_ballot_id, portfolio_key)
        self.confirm_action_label = f"Vote for {policy_row['name']}"
        self.confirm_summary = (
            f"Cast one member vote for the {policy_row['name']} model portfolio in the current ballot window. "
            "The chain records your chosen policy id, not a free-form asset trade."
        )
        self.confirm_call_args_json = json.dumps([int(call.args[0]), str(call.args[1])], default=str)
        self.confirm_params_rows.extend(
            [
                {"key": "Ballot id", "value": str(self.investment_ballot_id)},
                {"key": "Portfolio", "value": str(policy_row["name"])},
                {"key": "Your snapshot weight", "value": f"{self.investment_wallet_weight_share:.2%}" if self.investment_wallet_eligible else "Not eligible"},
                {"key": "Allocation hash", "value": str(policy_row["allocation_hash"])[:18] + "…"},
            ]
        )
        if not self.investment_wallet_eligible:
            self.confirm_is_live = False
            self.confirm_mode_label = "Blocked until an eligible member wallet is connected"
            self.confirm_params_rows.append(
                {"key": "Eligibility", "value": self.investment_wallet_note}
            )
        self.confirm_advanced_json = json.dumps(call.as_dict(), default=str)

    def confirm_action(self):
        """User clicked confirm in the drawer.

        Live actions dispatch into the JS bridge which asks MetaMask to
        sign. Off-chain actions just record the acknowledgement without
        opening a wallet prompt.
        """
        spec = self._ACTIONS.get(self.confirm_action_key)
        if not spec:
            self.confirm_open = False
            return

        self.last_tx_status    = "pending"
        self.last_tx_action_key = self.confirm_action_key
        self.last_tx_action    = spec["label"]
        self.last_tx_contract  = spec["contract"]
        self.last_tx_function  = spec["function"]
        self.last_tx_error     = ""
        self.last_tx_fee_wei   = ""
        self.last_tx_gas_used  = 0
        self.last_tx_fee_eth   = 0.0
        self.last_tx_fee_gbp   = 0.0

        _event_log().append(
            "action_confirmed",
            action=self.confirm_action_key,
            label=spec["label"],
            contract=spec["contract"],
            function=spec["function"],
            mode=self.confirm_mode_label,
        )

        if not spec.get("live") or not self.confirm_is_live:
            # Off-chain acknowledgement — nothing to wait on.
            self.last_tx_status = "confirmed"  # nothing to wait on
            self.last_tx_hash   = ""
            self.last_tx_short  = ""
            self.last_tx_explorer_url = ""
            self.confirm_open = False
            self._refresh_events()
            return

        # Live — dispatch the JS bridge. The bridge resolves with
        # { ok, hash?, error? }; result flows into `on_tx_submitted`.
        addr = self.confirm_target_addr
        fn   = spec["function"]
        key  = spec["contract"]
        extra_args = f", args: {self.confirm_call_args_json}" if self.confirm_call_args_json else ""
        extra_value = f", value: '{self.confirm_call_value_wei}'" if self.confirm_call_value_wei else ""
        self.confirm_open = False
        # We pass the chosen action via the JS call so the bridge can map it
        # to the right ABI + argument set. All heavy lifting lives in JS.
        inner = (
            f"window.aequitasWallet.runAction('{self.confirm_action_key}', "
            f"{{contract:'{key}', address:'{addr}', func:'{fn}'{extra_args}{extra_value}}})"
        )
        return rx.call_script(
            self._bridge_call(inner),
            callback=AppState.on_tx_submitted,
        )

    def on_tx_submitted(self, result: Any):
        """Callback from the JS bridge once MetaMask returns a tx hash."""
        r = result or {}
        if not isinstance(r, dict):
            self.last_tx_status = "failed"
            self.last_tx_error  = "Unexpected wallet response"
            return
        if r.get("ok"):
            txh = str(r.get("hash") or "")
            spec = self._ACTIONS.get(self.confirm_action_key)
            self.last_tx_hash  = txh
            self.last_tx_short = short_address(txh)
            self.last_tx_status = "confirmed" if r.get("confirmed") else "pending"
            self.last_tx_explorer_url = etherscan_tx(
                self.wallet_chain_id or SEPOLIA_CHAIN_ID, txh
            ) or ""
            _event_log().append(
                "tx_submitted",
                action=self.confirm_action_key,
                label=spec["label"] if spec else self.confirm_action_key,
                hash=txh,
                status=self.last_tx_status,
            )
            self._refresh_events()
            self._refresh_investment_governance()
        else:
            self.last_tx_status = "failed"
            self.last_tx_error  = str(r.get("error") or "Transaction rejected")
            _event_log().append(
                "tx_failed",
                action=self.confirm_action_key,
                error=self.last_tx_error,
            )
            self._refresh_events()
            self._refresh_investment_governance()

    def clear_last_tx(self):
        self.last_tx_status = "idle"
        self.last_tx_hash = ""
        self.last_tx_short = ""
        self.last_tx_action = ""
        self.last_tx_action_key = ""
        self.last_tx_contract = ""
        self.last_tx_function = ""
        self.last_tx_explorer_url = ""
        self.last_tx_error = ""
        self.last_tx_gas_used = 0
        self.last_tx_fee_wei = ""
        self.last_tx_fee_eth = 0.0
        self.last_tx_fee_gbp = 0.0

    # ======================================================================
    # Internals — recompute derived state
    # ======================================================================
    def _refresh_registry(self):
        """Hydrate fields from the on-chain registry (sepolia.json)."""
        reg = None
        if self.devtools_enabled and self.devtools_registry_mode == "local":
            reg = load_registry(_LOCAL_REGISTRY_PATH)
        elif self.devtools_enabled and self.devtools_registry_mode == "sepolia":
            reg = load_registry(_SEPOLIA_REGISTRY_PATH)
        else:
            reg = load_any_deployment()

        if self.devtools_enabled and self.devtools_registry_mode == "local" and (reg is None or not reg.is_present()):
            legacy = load_latest()
            if legacy is not None:
                reg = OnchainRegistry(
                    chain_id=LOCAL_ANVIL_CHAIN_ID,
                    chain_name=_chain_name(LOCAL_ANVIL_CHAIN_ID),
                    deployer=legacy.owner,
                    deployed_at="",
                    explorer_base="",
                    rpc_hint="",
                    verified=False,
                    contracts={
                        name: ContractRecord(name=name, address=addr, tx_hash="", verified=False)
                        for name, addr in legacy.addresses.items()
                    },
                    source_path=legacy.source_path,
                    raw={},
                )

        if reg is None:
            self.registry_present = False
            self.registry_chain_id = 0
            self.registry_chain_name = ""
            self.registry_deployer = ""
            self.registry_deployed_at = ""
            self.registry_explorer_base = ""
            self.registry_verified = False
            self.registry_rows = []
            self.registry_on_sepolia = False
            self.registry_source_path = ""
            return

        self.registry_present     = reg.is_present()
        self.registry_chain_id    = int(reg.chain_id)
        self.registry_chain_name  = reg.chain_name
        self.registry_deployer    = reg.deployer or ""
        self.registry_deployed_at = reg.deployed_at or ""
        self.registry_explorer_base = reg.explorer_base or ""
        self.registry_verified    = bool(reg.verified)
        self.registry_rows        = reg.as_rows()
        self.registry_on_sepolia  = _is_sepolia(reg.chain_id)
        self.registry_source_path = reg.source_path

    def _refresh(self):
        led = _ledger()

        # scenario catalogue (populate once, static after)
        if not self.twin_scenario_rows:
            self.twin_scenario_rows = list_presets()
            try:
                cfg = get_preset(self.twin_scenario)
                self.twin_scenario_description = cfg.description
            except ValueError:
                pass
        if not self.twin_v2_baseline_rows:
            self.twin_v2_baseline_rows = baseline_catalog()
            if not self.twin_v2_baseline_description:
                self.twin_v2_baseline_description = next(
                    (
                        row["description"]
                        for row in self.twin_v2_baseline_rows
                        if row["key"] == self.twin_v2_baseline_key
                    ),
                    "",
                )
        if not self.twin_v2_persona_catalog_rows:
            self.twin_v2_persona_catalog_rows = persona_catalog()
        if not self.gas_network_rows:
            self.gas_network_rows = network_preset_catalog()

        # deployment ribbon
        dep = load_latest()
        if dep is not None:
            self.deployment_detected = True
            self.deployment_owner = dep.owner or ""
            self.deployment_count = len(dep.addresses)
            self.deployment_address_rows = [
                {"contract": k, "address": v} for k, v in dep.addresses.items()
            ]
        else:
            self.deployment_detected = False
            self.deployment_owner = ""
            self.deployment_count = 0
            self.deployment_address_rows = []

        self.devtools_enabled = _env_flag("AEQUITAS_DEVTOOLS")
        self.devtools_forge_available = _forge_available()
        self.devtools_anvil_detected = _anvil_reachable()
        self.devtools_local_registry_exists = _LOCAL_REGISTRY_PATH.is_file()
        self.devtools_sepolia_registry_exists = _SEPOLIA_REGISTRY_PATH.is_file()
        self.devtools_can_deploy_local = self.devtools_forge_available and bool(str(os.getenv("ANVIL_PK", "")).strip())
        self.devtools_can_deploy_sepolia = self.devtools_forge_available and bool(str(os.getenv("DEPLOYER_PK", "")).strip())

        # richer on-chain registry (sepolia.json, or fallback legacy)
        self._refresh_registry()
        self.current_piu_price_value = float(led.piu_price)

        self.members_count = len(led)
        if self.members_count == 0:
            self.loaded = False
            self.member_rows = []
            self.valuation_rows = []
            self.cohort_mwr_rows = []
            self.cohort_epv_rows = []
            self.cohort_contrib_rows = []
            self.fund_projection_rows = []
            self._refresh_events()
            self._refresh_payloads()
            self._refresh_sandbox_actions()
            self._refresh_actual_fee_rows()
            return

        self.loaded = True

        valuations = led.value_all()
        self.epv_c = float(sum(v.epv_contributions for v in valuations))
        self.epv_b = float(sum(v.epv_benefits for v in valuations))
        self.mwr = (self.epv_b / self.epv_c) if self.epv_c else 0.0
        contribs = float(sum(m.total_contributions for m in led))
        self.funded_ratio = (contribs + 1e-9) / (self.epv_b + 1e-9)

        cv = led.cohort_valuation()
        self.cohorts_count = len(cv)
        mwrs = {c: cv[c]["money_worth_ratio"] for c in cv}
        if len(mwrs) >= 2:
            self.gini = float(mwr_gini(mwrs))
            self.intergen = float(intergenerational_index(mwrs))
            disp = mwr_dispersion(mwrs)
            self.mwr_min = float(disp["min"])
            self.mwr_max = float(disp["max"])
            self.mwr_std = float(disp["std"])
        else:
            self.gini = 0.0
            self.intergen = 1.0
            self.mwr_min = 0.0
            self.mwr_max = 0.0
            self.mwr_std = 0.0

        self.cohort_mwr_rows = [
            {"cohort": int(c), "mwr": round(float(mwrs[c]), 4)}
            for c in sorted(mwrs)
        ]
        self.cohort_epv_rows = [
            {"cohort": int(c),
             "epv_benefits": round(float(cv[c]["epv_benefits"]), 2),
             "epv_contributions": round(float(cv[c]["epv_contributions"]), 2),
             "mwr": round(float(cv[c]["money_worth_ratio"]), 4)}
            for c in sorted(cv)
        ]
        self.cohort_contrib_rows = [
            {"cohort": int(c), "total_contributions": float(v)}
            for c, v in sorted(led.cohort_aggregate_contrib.items())
        ]

        self.member_rows = [
            {
                "wallet": m.wallet,
                "cohort": int(m.cohort),
                "birth_year": int(m.birth_year),
                "age": int(led.valuation_year - m.birth_year),
                "salary": float(m.salary),
                "contribution_rate": round(float(m.contribution_rate), 4),
                "retirement_age": int(m.retirement_age),
                "sex": m.sex,
                "total_contributions": round(float(m.total_contributions), 2),
                "piu_balance": round(float(m.piu_balance), 4),
                "piu_value": round(float(led.piu_nominal_value(m.piu_balance)), 2),
                "piu_price": round(float(led.piu_price), 4),
                }
            for m in led
        ]
        self.valuation_rows = [
            {
                "wallet": v.wallet,
                "epv_contributions": round(float(v.epv_contributions), 0),
                "epv_benefits":      round(float(v.epv_benefits), 0),
                "money_worth_ratio": round(float(v.money_worth_ratio), 3),
                "current_piu_price": round(float(v.current_piu_price), 4),
                "current_piu_value": round(float(v.current_piu_value), 2),
                "projected_annual_benefit_piu": round(float(v.projected_annual_benefit_piu), 4),
                "projected_annual_benefit": round(float(v.projected_annual_benefit), 0),
                "replacement_ratio": round(float(v.replacement_ratio), 4),
            }
            for v in valuations
        ]

        fund_df = project_fund(
            led.get_all_members(),
            valuation_year=led.valuation_year,
            salary_growth=led.salary_growth,
            investment_return=led.investment_return,
            discount_rate=led.discount_rate,
            inflation_rate=led.expected_inflation,
            horizon=60,
            current_cpi=led.current_cpi,
            current_piu_price=led.piu_price,
        )
        if not fund_df.empty:
            records = typed_records(
                fund_df.to_dict("records"),
                int_fields={"year", "active_contributors", "retirees"},
                float_fields={
                    "contributions",
                    "benefit_payments",
                    "fund_value",
                    "total_pius",
                    "cpi_index",
                    "piu_price",
                },
            )
            first_cpi = max(float(records[0]["cpi_index"]), 1e-9)
            first_price = max(float(records[0]["piu_price"]), 1e-9)
            self.fund_projection_rows = []
            for row in records:
                self.fund_projection_rows.append(
                    {
                        **row,
                        "fund_value_k": round(float(row["fund_value"]) / 1_000, 2),
                        "fund_value_m": round(float(row["fund_value"]) / 1_000_000, 3),
                        "contributions_k": round(float(row["contributions"]) / 1_000, 2),
                        "benefit_payments_k": round(float(row["benefit_payments"]) / 1_000, 2),
                        "total_pius_k": round(float(row["total_pius"]) / 1_000, 3),
                        "cpi_rebased": round(float(row["cpi_index"]) * 100.0 / first_cpi, 2),
                        "piu_price_index": round(float(row["piu_price"]) * 100.0 / first_price, 2),
                    }
                )

        # keep multipliers in sync with current cohorts
        cohort_keys = {str(int(c)) for c in cv}
        if set(self.multipliers.keys()) != cohort_keys:
            self.multipliers = {k: float(self.multipliers.get(k, 1.0)) for k in cohort_keys}

        # drill-down default
        if self.member_rows and (
            not self.selected_wallet
            or self.selected_wallet not in {m["wallet"] for m in self.member_rows}
        ):
            self.selected_wallet = self.member_rows[0]["wallet"]
        self._refresh_drilldown()
        self._refresh_events()
        self._refresh_payloads()
        self._refresh_sandbox_actions()
        self._refresh_actual_fee_rows()

    def _refresh_drilldown(self):
        led = _ledger()
        if not self.selected_wallet or self.selected_wallet not in led.members:
            self.member_projection_rows = []
            self.member_age = 0
            self.member_first_benefit = 0.0
            self.member_fund_peak = 0.0
            return
        member = led.get_member_summary(self.selected_wallet)
        df = project_member(
            member,
            valuation_year=led.valuation_year,
            salary_growth=led.salary_growth,
            investment_return=led.investment_return,
            discount_rate=led.discount_rate,
            inflation_rate=led.expected_inflation,
            horizon=60,
            current_cpi=led.current_cpi,
            current_piu_price=led.piu_price,
        )
        self.member_age = int(member.age(led.valuation_year))
        retired = df[df["phase"] == "retired"]
        accum = df[df["phase"] == "accumulation"]
        self.member_first_benefit = (
            float(retired["benefit_payment"].iloc[0]) if not retired.empty else 0.0
        )
        self.member_fund_peak = (
            float(accum["fund_value"].max()) if not accum.empty else 0.0
        )
        records = typed_records(
            df.to_dict("records"),
            int_fields={"year", "age"},
            float_fields={
                "salary",
                "contribution",
                "piu_added",
                "piu_balance",
                "fund_value",
                "benefit_payment",
                "cpi_index",
                "piu_price",
                "benefit_piu",
                "nominal_piu_value",
            },
            str_fields={"phase"},
        )
        first_cpi = max(float(records[0]["cpi_index"]), 1e-9) if records else 1.0
        first_price = max(float(records[0]["piu_price"]), 1e-9) if records else 1.0
        self.member_projection_rows = []
        for row in records:
            self.member_projection_rows.append(
                {
                    **row,
                    "fund_value_k": round(float(row["fund_value"]) / 1_000, 2),
                    "contribution_k": round(float(row["contribution"]) / 1_000, 2),
                    "benefit_payment_k": round(float(row["benefit_payment"]) / 1_000, 2),
                    "nominal_piu_value_k": round(float(row["nominal_piu_value"]) / 1_000, 2),
                    "piu_balance_k": round(float(row["piu_balance"]) / 1_000, 3),
                    "benefit_piu_k": round(float(row["benefit_piu"]) / 1_000, 3),
                    "cpi_rebased": round(float(row["cpi_index"]) * 100.0 / first_cpi, 2),
                    "piu_price_index": round(float(row["piu_price"]) * 100.0 / first_price, 2),
                }
            )

    def _refresh_events(self):
        log = _event_log()
        self.event_rows = [
            {
                "seq": e.seq,
                "event": _pretty_event(e),
                "type": e.event_type,
                "hash": e.hash[:10] + "…",
            }
            for e in log
        ][::-1]   # newest first
        self.raw_event_rows = [
            {
                "seq": e.seq,
                "event_type": e.event_type,
                "data": str(e.data),
                "hash": e.hash,
                "prev_hash": e.prev_hash,
            }
            for e in log
        ]
        self._refresh_sandbox_actions()

    def _refresh_payloads(self):
        led = _ledger()
        if len(led) == 0:
            self.ledger_payload_preview = []
            self.baseline_payload = {}
            self.proposal_payload = {}
            self.pool_deposit_payload = {}
            self.open_retirement_payload = {}
            self.mortality_basis_payload = {}
            self.stress_update_payload = {}
            self.backstop_deposit_payload = {}
            self.backstop_release_payload = {}
            self.piu_price_payload = {}
            self.actuarial_method_payload = {}
            self.actuarial_parameter_payload = {}
            self.actuarial_valuation_payload = {}
            self.actuarial_result_payload = {}
            self.actuarial_spot_check_payload = {}
            self.sandbox_mortality_rows = []
            self.sandbox_mortality_summary_rows = []
            self.sandbox_mortality_basis_version = ""
            self.sandbox_mortality_study_hash = ""
            self.sandbox_mortality_credibility = 0.0
            self.sandbox_mortality_advisory = True
            self.actuarial_method_rows = []
            self.actuarial_parameter_rows = []
            self.actuarial_result_rows = []
            self.actuarial_verifier_rows = []
            self.actuarial_proof_scope_rows = []
            self.actuarial_proof_summary_text = ""
            self.actuarial_method_contract_key = ""
            self.actuarial_result_contract_key = ""
            self.actuarial_method_count = 0
            self._refresh_investment_governance()
            return

        cv = led.cohort_valuation()
        calls = ledger_to_chain_calls(led)
        self.ledger_payload_preview = calls_to_json(calls[:5])

        self.baseline_payload = encode_baseline(cv).as_dict()

        # stylised "trim youngest -3%" proposal for the preview
        cohorts = sorted(cv.keys())
        mults = {int(c): 1.0 for c in cohorts}
        if cohorts:
            mults[int(cohorts[-1])] = 0.97
        self.proposal_payload = encode_proposal(
            Proposal(name="Preview", description="", multipliers=mults),
            cv, delta=0.05,
        ).as_dict()

        first_wallet = sorted(led.members.keys())[0]
        self.pool_deposit_payload = encode_pool_deposit(first_wallet, 10.0).as_dict()
        self.open_retirement_payload = encode_open_retirement(
            first_wallet, 10.0, 1.2,
        ).as_dict()
        self.piu_price_payload = encode_piu_price_update(
            led.piu_price,
            cpi_level=led.current_cpi,
        ).as_dict()
        mortality_snapshot = deterministic_sandbox_snapshot(
            members=led.get_all_members(),
            valuation_year=int(self.valuation_year),
        )
        self.mortality_basis_payload = encode_mortality_basis_publish(mortality_snapshot).as_dict()
        self.sandbox_mortality_rows = [
            {
                "cohort": int(row.cohort),
                "exposure_years": float(row.exposure_years),
                "observed_deaths": int(row.observed_deaths),
                "expected_deaths": float(row.expected_deaths),
                "observed_expected": float(row.observed_expected),
                "credibility_pct": round(float(row.credibility_weight) * 100.0, 2),
                "blended_multiplier": float(row.blended_multiplier),
                "stable_enough": "Yes" if row.stable_enough else "Advisory",
            }
            for row in mortality_snapshot.cohort_adjustments
        ]
        self.sandbox_mortality_summary_rows = [
            {"label": "Baseline prior", "value": mortality_snapshot.baseline_model_id},
            {"label": "Basis version", "value": mortality_snapshot.version_id},
            {"label": "Credibility", "value": f"{mortality_snapshot.credibility_weight:.1%}"},
            {"label": "Effective date", "value": mortality_snapshot.effective_date},
            {
                "label": "On-chain posture",
                "value": "Advisory until thresholds are met" if mortality_snapshot.advisory else "Ready to publish as active basis",
            },
        ]
        self.sandbox_mortality_basis_version = mortality_snapshot.version_id
        self.sandbox_mortality_study_hash = mortality_snapshot.study_hash
        self.sandbox_mortality_credibility = float(mortality_snapshot.credibility_weight)
        self.sandbox_mortality_advisory = bool(mortality_snapshot.advisory)
        self.stress_update_payload = encode_stress_update(
            0.25, "p95_gini>threshold", str({"n_cohorts": len(cv)})
        ).as_dict()
        self.backstop_deposit_payload = encode_backstop_deposit(5.0).as_dict()
        self.backstop_release_payload = encode_backstop_release(1.0).as_dict()
        self._refresh_actuarial_proof()
        self._refresh_investment_governance()
        self._refresh_sandbox_gas()

    def _refresh_actuarial_proof(self):
        led = _ledger()
        if len(led) == 0:
            return

        proof = build_default_proof_bundle(
            led,
            valuation_date=int(self.valuation_year),
            fairness_delta=float(self.corridor_delta_pct) / 100.0,
            mortality_basis_version=1,
        )
        methods = proof["methods"]
        parameter_snapshot = proof["parameter_snapshot"]
        valuation_snapshot = proof["valuation_snapshot"]
        scheme_summary = proof["scheme_summary"]
        cohort_summaries = proof["cohort_summaries"]
        result_bundle = proof["result_bundle"]
        spot_check = proof["spot_check"]

        self.actuarial_method_payload = encode_actuarial_method_register(methods[0]).as_dict()
        self.actuarial_parameter_payload = encode_actuarial_parameter_set_publish(parameter_snapshot).as_dict()
        self.actuarial_valuation_payload = encode_actuarial_valuation_snapshot_publish(valuation_snapshot).as_dict()
        self.actuarial_result_payload = encode_actuarial_result_bundle_publish(result_bundle).as_dict()
        self.actuarial_spot_check_payload = encode_actuarial_mwr_spot_check(spot_check).as_dict()
        self.actuarial_method_count = len(methods)
        self.actuarial_method_contract_key = methods[0].method_key
        self.actuarial_result_contract_key = result_bundle.result_bundle_key

        self.actuarial_method_rows = [
            {
                "family": method.method_family,
                "version": method.version,
                "method_key": method.method_key,
                "effective_date": str(method.effective_date),
                "spec_hash_short": method.spec_hash[:18] + "…",
                "reference_impl_hash_short": method.reference_impl_hash[:18] + "…",
                "schema_hash_short": method.parameter_schema_hash[:18] + "…",
            }
            for method in methods
        ]
        self.actuarial_parameter_rows = [
            {"label": "Valuation year", "value": str(parameter_snapshot.valuation_date)},
            {"label": "Discount rate", "value": f"{parameter_snapshot.discount_rate_bps / 100:.2f}%"},
            {"label": "Salary growth", "value": f"{parameter_snapshot.salary_growth_bps / 100:.2f}%"},
            {"label": "Investment return", "value": f"{parameter_snapshot.investment_return_bps / 100:.2f}%"},
            {"label": "PIU price", "value": f"{led.piu_price:.6f}"},
            {"label": "Fairness corridor delta", "value": f"{parameter_snapshot.fairness_delta_bps / 100:.2f}%"},
            {"label": "Mortality basis version", "value": str(parameter_snapshot.mortality_basis_version)},
            {"label": "Parameter set hash", "value": parameter_snapshot.parameter_hash[:18] + "…"},
            {"label": "Member snapshot hash", "value": valuation_snapshot.member_snapshot_hash[:18] + "…"},
            {"label": "Cohort summary hash", "value": valuation_snapshot.cohort_summary_hash[:18] + "…"},
        ]
        self.actuarial_result_rows = [
            {"label": "Scheme EPV contributions", "value": f"{scheme_summary.epv_contributions_fixed / 1e18:,.0f}"},
            {"label": "Scheme EPV benefits", "value": f"{scheme_summary.epv_benefits_fixed / 1e18:,.0f}"},
            {"label": "Scheme MWR", "value": f"{scheme_summary.mwr_bps / 10_000:.3f}"},
            {"label": "Funded ratio", "value": f"{scheme_summary.funded_ratio_bps / 100:.2f}%"},
            {"label": "Cohorts committed", "value": str(len(cohort_summaries))},
            {"label": "Result bundle hash", "value": result_bundle.result_hash[:18] + "…"},
            {"label": "Cohort digest", "value": result_bundle.cohort_digest[:18] + "…"},
        ]
        self.actuarial_verifier_rows = [
            {"label": "On-chain kernel", "value": "MWR ratio, fairness corridor, bounded single-member EPV"},
            {"label": "Current spot check", "value": f"Verify MWR {scheme_summary.mwr_bps / 10_000:.3f} from declared EPVs"},
            {"label": "Tolerance", "value": f"{spot_check.tolerance_bps} bps"},
            {"label": "Verifier scope", "value": "Deterministic spot checks only — no Monte Carlo or member-by-member full valuation loops"},
        ]
        self.actuarial_proof_scope_rows = [
            {"scope": "On-chain", "detail": "Method versions, parameter hashes, valuation-input commitments, result-bundle commitments, and bounded spot checks."},
            {"scope": "Off-chain", "detail": "The full actuarial engine, member-level valuation loops, mortality calibration internals, and Monte Carlo stress simulation."},
            {"scope": "Why chain exists", "detail": "To timestamp the active methodology and prevent silent rewriting of assumptions or published results after the fact."},
        ]
        self.actuarial_proof_summary_text = (
            "Aequitas keeps the full actuarial engine off-chain in Python, then publishes the method version, parameter snapshot, "
            "input commitments, and result bundle on-chain. The chain can spot-check small deterministic claims such as scheme MWR "
            "or corridor pass/fail, but it does not re-run the full pension engine."
        )

    def _refresh_investment_governance(self):
        led = _ledger()
        if len(led) == 0:
            self.investment_policy_rows = []
            self.investment_weight_rows = []
            self.investment_support_rows = []
            self.investment_validation_rows = []
            self.investment_ballot_rows = []
            self.investment_guardrail_rows = []
            self.investment_assumption_rows = []
            self.investment_ballot_id = 0
            self.investment_ballot_opens_at = 0
            self.investment_ballot_closes_at = 0
            self.investment_winner_key = ""
            self.investment_winner_name = ""
            self.investment_winner_reason = ""
            self.investment_winner_passes = False
            self.investment_wallet_eligible = False
            self.investment_wallet_weight = 0
            self.investment_wallet_weight_share = 0.0
            self.investment_wallet_note = ""
            self.investment_snapshot_note = ""
            self.investment_policy_payload = {}
            self.investment_weights_payload = {}
            self.investment_vote_payload = {}
            self.investment_finalize_payload = {}
            return

        now_ts = int(pd.Timestamp.utcnow().timestamp())
        opens_at = now_ts + 300
        closes_at = opens_at + int(self.investment_round_duration_days) * 86_400
        members = led.get_all_members()
        try:
            draft = build_ballot_draft(
                led,
                round_name=self.investment_round_name,
                opens_at=opens_at,
                closes_at=closes_at,
            )
        except ValueError as err:
            self.investment_policy_rows = []
            self.investment_weight_rows = []
            self.investment_support_rows = []
            self.investment_validation_rows = []
            self.investment_ballot_rows = []
            self.investment_guardrail_rows = []
            self.investment_assumption_rows = []
            self.investment_policy_payload = {}
            self.investment_weights_payload = {}
            self.investment_vote_payload = {}
            self.investment_finalize_payload = {}
            self.investment_snapshot_note = str(err)
            self.investment_wallet_eligible = False
            self.investment_wallet_weight = 0
            self.investment_wallet_weight_share = 0.0
            self.investment_wallet_note = str(err)
            return

        created_events = [
            ev for ev in _event_log()
            if ev.event_type == "tx_submitted" and str(ev.data.get("action") or "") == "create_investment_ballot"
        ]
        self.investment_ballot_id = max(0, len(created_events) - 1) if created_events else 0
        self.investment_ballot_opens_at = opens_at
        self.investment_ballot_closes_at = closes_at
        self.investment_winner_key = draft.winner_key
        self.investment_winner_name = next(
            (row["name"] for row in investment_portfolio_catalog() if row["key"] == draft.winner_key),
            draft.winner_key.replace("_", " ").title(),
        )
        self.investment_winner_reason = draft.winner_validation.reason
        self.investment_winner_passes = bool(draft.winner_validation.passes)

        validations = draft.validation_by_portfolio
        support_by_key = {str(row["key"]): row for row in draft.support_rows}
        self.investment_policy_rows = [
            {
                **row,
                "allocation_text": ", ".join(
                    f"{asset.replace('_', ' ')} {row['allocation'][asset]}%"
                    for asset in row["allocation"]
                ),
                "support_label": str(support_by_key[row["key"]]["support_label"]),
                "validation_label": "Passes guardrails" if validations[row["key"]].passes else "Blocked by guardrails",
                "validation_kind": "good" if validations[row["key"]].passes else "bad",
                "reason": validations[row["key"]].reason,
                "is_winner": "yes" if row["key"] == draft.winner_key else "no",
            }
            for row in investment_portfolio_catalog()
        ]
        self.investment_weight_rows = [
            {
                "wallet": row.wallet,
                "window_contribution": round(float(row.window_contribution), 2),
                "window_contribution_label": _compact_currency(float(row.window_contribution)),
                "raw_score": round(float(row.raw_score), 4),
                "vote_share_pct": round(float(row.vote_share) * 100.0, 2),
                "vote_share_label": f"{float(row.vote_share):.2%}",
                "published_weight": int(row.published_weight),
            }
            for row in sorted(draft.weight_rows, key=lambda item: (-item.published_weight, item.wallet))
        ]
        self.investment_support_rows = [
            {
                "key": str(row["key"]),
                "portfolio": str(row["name"]),
                "support_share": round(float(row["support_share"]) * 100.0, 2),
                "support_label": str(row["support_label"]),
                "weighted_votes": int(row["weighted_votes"]),
                "allocation_hash": str(row["allocation_hash"]),
                "winner": "Winner" if str(row["key"]) == draft.winner_key else "",
                "validation": "Passes" if validations[str(row["key"])].passes else "Blocked",
                "reason": validations[str(row["key"])].reason,
            }
            for row in draft.support_rows
        ]
        self.investment_validation_rows = [
            {
                "portfolio": next(
                    (p["name"] for p in investment_portfolio_catalog() if p["key"] == key),
                    key.replace("_", " ").title(),
                ),
                "funded_ratio": f"{result.funded_ratio_before:.1%} -> {result.funded_ratio_after:.1%}",
                "gini": f"{result.gini_before:.3f} -> {result.gini_after:.3f}",
                "stress": f"{result.stress_pass_rate:.1%}",
                "verdict": "Pass" if result.passes else "Blocked",
                "reason": result.reason,
            }
            for key, result in validations.items()
        ]
        self.investment_ballot_rows = [
            {"label": "Ballot round", "value": draft.round_name},
            {"label": "Eligible members", "value": str(len(draft.weight_rows))},
            {"label": "Weight rule", "value": "1 + sqrt(current-window contribution), capped at 5% share"},
            {"label": "Opens", "value": str(pd.to_datetime(opens_at, unit="s", utc=True).strftime("%Y-%m-%d %H:%M UTC"))},
            {"label": "Closes", "value": str(pd.to_datetime(closes_at, unit="s", utc=True).strftime("%Y-%m-%d %H:%M UTC"))},
            {"label": "Indicative winner", "value": self.investment_winner_name},
        ]
        self.investment_guardrail_rows = [
            {"label": "Funded-ratio deterioration limit", "value": "No more than 6 percentage points"},
            {"label": "Fairness dispersion limit", "value": "No more than +0.025 Gini worsening"},
            {"label": "Stress pass-rate floor", "value": "At least 70%"},
        ]
        self.investment_assumption_rows = [
            {"note": "Counted off-chain: decision-window contribution snapshot, concave weighting, cap enforcement, and portfolio guardrail validation."},
            {"note": "Published on-chain: ballot round, allowed portfolio ids, allocation hashes, member weight snapshot, votes, and the final adopted policy hash."},
            {"note": "The on-chain outcome is an investment policy publication only. It does not instruct direct ETF, bond, gold, or custody execution."},
        ]
        total_weight = max(1, sum(int(row.published_weight) for row in draft.weight_rows))
        self.investment_snapshot_note = (
            f"The current snapshot uses each member's current-period contribution flow, gives every member one base vote, "
            f"adds a concave boost, and then caps any single published share at {MAX_EFFECTIVE_SHARE:.0%}."
        )

        voter_weight_map = {row.wallet: int(row.published_weight) for row in draft.weight_rows}
        self.investment_policy_payload = encode_create_investment_ballot(draft).as_dict()
        self.investment_weights_payload = encode_investment_ballot_weights(
            self.investment_ballot_id,
            voter_weight_map,
        ).as_dict()
        self.investment_finalize_payload = encode_finalize_investment_ballot(
            self.investment_ballot_id,
        ).as_dict()

        wallet_norm = ""
        if self.wallet_address:
            try:
                wallet_norm = normalize_address(self.wallet_address)
            except ValueError:
                wallet_norm = str(self.wallet_address).lower()
        snapshot_by_wallet = {
            normalize_address(row.wallet): row for row in draft.weight_rows
        }
        selected_weight_row = snapshot_by_wallet.get(wallet_norm)
        self.investment_wallet_eligible = selected_weight_row is not None
        if selected_weight_row is not None:
            self.investment_wallet_weight = int(selected_weight_row.published_weight)
            self.investment_wallet_weight_share = float(selected_weight_row.published_weight) / total_weight
            self.investment_wallet_note = (
                f"Eligible in the current ballot snapshot with {self.investment_wallet_weight_share:.2%} of published voting weight."
            )
            self.investment_vote_payload = encode_investment_vote(
                self.investment_ballot_id,
                draft.winner_key,
            ).as_dict()
        else:
            self.investment_wallet_weight = 0
            self.investment_wallet_weight_share = 0.0
            self.investment_wallet_note = (
                "The connected wallet is not part of the current sandbox membership snapshot, so it cannot cast a live demo vote."
                if self.wallet_connected else
                "Connect a wallet that appears in the current ballot snapshot to cast a live vote."
            )
            self.investment_vote_payload = {}

    def _refresh_sandbox_gas(self):
        if not self.loaded or not self.member_rows:
            self.sandbox_gas_step_rows = []
            self.sandbox_gas_comparison_rows = []
            self.sandbox_gas_assumption_rows = []
            self.sandbox_gas_total_cost = 0.0
            self.sandbox_gas_total_gas_units = 0
            self.sandbox_gas_summary_text = ""
            return
        counts = build_sandbox_option_b_counts(
            member_count=len(self.member_rows),
            cohort_count=max(1, self.cohorts_count),
        )
        result = run_gas_cost_model(counts, preset_key=self.gas_network_preset)
        self.sandbox_gas_step_rows = [
            {
                "key": str(row["action_key"]),
                "title": str(row["label"]),
                "action_type": str(row["action_type"]),
                "contract_function": str(row["contract_function"]),
                "count": int(row["count"]),
                "gas_units_each": int(row["gas_units_each"]),
                "total_gas_units": int(row["total_gas_units"]),
                "estimated_cost_gbp": round(float(row["total_cost_gbp"]), 2),
                "estimated_cost_label": _compact_currency(float(row["total_cost_gbp"])),
                "estimated_gas_label": f"{int(row['total_gas_units']):,} gas",
                "note": str(row["note"]),
                "step_order": int(row.get("step_order", 0) or 0),
            }
            for row in result.action_breakdown.sort_values("step_order").to_dict("records")
        ]
        self.sandbox_gas_comparison_rows = [
            {
                "preset_label": str(row["preset_label"]),
                "total_cost_k": round(float(row["total_cost_k"]), 2),
                "total_cost_label": _compact_currency(float(row["total_cost_gbp"])),
                "latest_share_contributions_pct": float(row["latest_share_contributions_pct"]),
            }
            for row in result.preset_comparison.to_dict("records")
        ]
        self.sandbox_gas_assumption_rows = [{"note": note} for note in result.assumptions]
        self.sandbox_gas_total_cost = float(result.summary.get("total_cost_gbp", 0.0))
        self.sandbox_gas_total_gas_units = int(result.action_breakdown["total_gas_units"].sum()) if not result.action_breakdown.empty else 0
        self.sandbox_gas_summary_text = (
            f"Under the {result.preset.label} preset, executing the full deterministic proof flow on chain would cost "
            f"{_compact_currency(self.sandbox_gas_total_cost)} in total. That includes member setup, contribution posts, oracle publications, "
            "a proposal evaluation, a reserve path, and a retirement opening."
        )

    def _refresh_twin_v2_gas(self):
        if not self.twin_v2_ran or not self.twin_v2_annual_rows:
            self.twin_v2_gas_annual_rows = []
            self.twin_v2_gas_action_rows = []
            self.twin_v2_gas_comparison_rows = []
            self.twin_v2_gas_assumption_rows = []
            self.twin_v2_gas_scope_rows = []
            self.twin_v2_gas_total_cost = 0.0
            self.twin_v2_gas_latest_year_cost = 0.0
            self.twin_v2_gas_latest_cost_per_member = 0.0
            self.twin_v2_gas_latest_cost_per_1000 = 0.0
            self.twin_v2_gas_total_share_contributions = 0.0
            self.twin_v2_gas_top_action_type = ""
            self.twin_v2_gas_recommendation_label = ""
            self.twin_v2_gas_recommendation_text = ""
            return
        annual_df = pd.DataFrame(self.twin_v2_annual_rows)
        result = run_gas_cost_model(
            build_option_b_twin_counts(
                annual_df,
                starting_population=self.twin_v2_population_size,
                cohort_count=max(1, len({int(row["cohort"]) for row in self.twin_v2_cohort_rows})),
            ),
            preset_key=self.gas_network_preset,
        )
        self.twin_v2_gas_annual_rows = [
            {
                "year": int(row["year"]),
                "total_cost_gbp": round(float(row["total_cost_gbp"]), 2),
                "total_cost_k": round(float(row["total_cost_k"]), 2),
                "cumulative_cost_gbp": round(float(row["cumulative_cost_gbp"]), 2),
                "cumulative_cost_k": round(float(row["cumulative_cost_k"]), 2),
                "cost_per_member_gbp": round(float(row["cost_per_member_gbp"]), 4),
                "cost_per_1000_members_gbp": round(float(row["cost_per_1000_members_gbp"]), 2),
                "cost_share_contributions_pct": round(float(row["cost_share_contributions"]) * 100.0, 3),
                "oracle_updates_cost_k": round(float(row.get("oracle_updates_cost_k", 0.0)), 2),
                "governance_cost_k": round(float(row.get("governance_cost_k", 0.0)), 2),
                "reserve_actions_cost_k": round(float(row.get("reserve_actions_cost_k", 0.0)), 2),
                "member_lifecycle_cost_k": round(float(row.get("member_lifecycle_cost_k", 0.0)), 2),
                "member_cashflows_cost_k": round(float(row.get("member_cashflows_cost_k", 0.0)), 2),
            }
            for row in result.annual.to_dict("records")
        ]
        self.twin_v2_gas_action_rows = [
            {
                "label": str(row["label"]),
                "action_type": str(row["action_type"]),
                "actor_type": str(row["actor_type"]),
                "count": int(row["count"]),
                "gas_units": int(row["total_gas_units"]),
                "total_cost_gbp": round(float(row["total_cost_gbp"]), 2),
                "total_cost_label": _compact_currency(float(row["total_cost_gbp"])),
                "contract_function": str(row["contract_function"]),
            }
            for row in result.action_totals.to_dict("records")
        ]
        self.twin_v2_gas_comparison_rows = [
            {
                "preset_label": str(row["preset_label"]),
                "total_cost_k": round(float(row["total_cost_k"]), 2),
                "total_cost_label": _compact_currency(float(row["total_cost_gbp"])),
                "latest_share_contributions_pct": float(row["latest_share_contributions_pct"]),
            }
            for row in result.preset_comparison.to_dict("records")
        ]
        self.twin_v2_gas_assumption_rows = [{"note": note} for note in result.assumptions]
        self.twin_v2_gas_scope_rows = [
            {"scope": "Counted on-chain", "detail": "Annual PIU, mortality, and stress publications; initial baseline; governance proposals; reserve actions; member registrations; one contribution post per active member per year; retirement openings."},
            {"scope": "Not counted on-chain", "detail": "Private actuarial calibration, raw member data, raw death records, exposure calculations, and other off-chain engine work."},
        ]
        self.twin_v2_gas_total_cost = float(result.summary.get("total_cost_gbp", 0.0))
        self.twin_v2_gas_latest_year_cost = float(result.summary.get("latest_cost_gbp", 0.0))
        self.twin_v2_gas_latest_cost_per_member = float(result.summary.get("latest_cost_per_member_gbp", 0.0))
        self.twin_v2_gas_latest_cost_per_1000 = float(result.summary.get("latest_cost_per_1000_members_gbp", 0.0))
        self.twin_v2_gas_total_share_contributions = float(result.summary.get("total_share_contributions", 0.0))
        self.twin_v2_gas_top_action_type = str(result.summary.get("top_action_type", ""))
        self.twin_v2_gas_recommendation_label = str(result.summary.get("recommendation_label", ""))
        self.twin_v2_gas_recommendation_text = str(result.summary.get("recommendation_text", ""))

    def _refresh_actual_fee_rows(self):
        rows: list[dict[str, Any]] = []
        seen_hashes: set[str] = set()
        for ev in reversed(list(_event_log())):
            if ev.event_type != "tx_confirmed":
                continue
            tx_hash = str(ev.data.get("hash") or "")
            if not tx_hash or tx_hash in seen_hashes:
                continue
            seen_hashes.add(tx_hash)
            fee_wei = str(ev.data.get("fee_wei") or "")
            fee_eth = fee_eth_from_wei(fee_wei) if fee_wei else 0.0
            fee_gbp = fee_gbp_from_wei(fee_wei, self.gas_network_preset) if fee_wei else 0.0
            rows.append(
                {
                    "action_key": str(ev.data.get("action") or ""),
                    "action": str(ev.data.get("label") or ev.data.get("action") or "Live action"),
                    "tx_hash": tx_hash,
                    "short_hash": short_address(tx_hash),
                    "status": str(ev.data.get("status") or "CONFIRMED").upper(),
                    "gas_used": int(ev.data.get("gas_used") or 0),
                    "fee_eth": round(fee_eth, 6),
                    "fee_gbp": round(fee_gbp, 2),
                    "fee_label": _compact_currency(fee_gbp) if fee_wei else "Waiting for receipt",
                    "explorer_url": etherscan_tx(self.wallet_chain_id or self.registry_chain_id, tx_hash) or "",
                }
            )
        self.actual_fee_rows = rows
        self.actual_fee_tx_count = len(rows)
        self.actual_fee_total_eth = round(sum(float(row["fee_eth"]) for row in rows), 6)
        self.actual_fee_total_gbp = round(sum(float(row["fee_gbp"]) for row in rows), 2)

    def _refresh_sandbox_actions(self):
        reg_by_name = {str(row.get("name")): row for row in self.registry_rows}
        gas_by_action = {str(row.get("key")): row for row in self.sandbox_gas_step_rows}
        latest_by_action: dict[str, dict[str, Any]] = {}
        recent_rows: list[dict] = []
        for ev in reversed(list(_event_log())):
            if ev.event_type not in {"tx_submitted", "tx_confirmed"}:
                continue
            action_key = str(ev.data.get("action") or "")
            tx_hash = str(ev.data.get("hash") or "")
            if action_key and action_key not in latest_by_action:
                status = str(ev.data.get("status") or ("confirmed" if ev.event_type == "tx_confirmed" else "pending")).upper()
                fee_wei = str(ev.data.get("fee_wei") or "")
                fee_gbp = fee_gbp_from_wei(fee_wei, self.gas_network_preset) if fee_wei else 0.0
                latest_by_action[action_key] = {
                    "tx_hash": tx_hash,
                    "status": status,
                    "fee_wei": fee_wei,
                    "fee_gbp": fee_gbp,
                    "gas_used": int(ev.data.get("gas_used") or 0),
                }
                recent_rows.append(
                    {
                        "action": action_key.replace("_", " ").title(),
                        "tx_hash": tx_hash,
                        "short_hash": short_address(tx_hash),
                        "status": status,
                        "fee_label": _compact_currency(fee_gbp) if fee_wei else "Waiting for receipt",
                        "explorer_url": etherscan_tx(self.wallet_chain_id or self.registry_chain_id, tx_hash) or "",
                    }
                )
        self.sandbox_recent_tx_rows = recent_rows[:6]

        rows: list[dict] = []
        for spec in self._SANDBOX_STEPS:
            contract = str(spec["contract"])
            registry_row = reg_by_name.get(contract, {})
            action_key = str(spec["key"])
            action_meta = latest_by_action.get(action_key, {})
            gas_meta = gas_by_action.get(action_key, {})
            tx_hash = action_meta.get("tx_hash", "")
            live = spec["kind"] == "action"
            if action_key == "demo_members":
                status = "READY" if self.loaded else "NOT LOADED"
                evidence = f"{self.members_count} demo members in the sandbox." if self.loaded else "Load the sandbox dataset first."
            elif action_key == "demo_contributions":
                status = "READY" if self.loaded and self.epv_c > 0 else "NOT LOADED"
                evidence = f"Current deterministic contribution base: £{self.epv_c:,.0f} EPV." if self.loaded else "Load the sandbox dataset first."
            elif action_key == "submit_proposal":
                status = (
                    action_meta.get("status")
                    or ("LOCAL PASS" if self.sandbox_ran and self.sandbox_is_pass else "LOCAL FAIL" if self.sandbox_ran else "READY")
                )
                evidence = self.sandbox_verdict if self.sandbox_ran else "Use the sandbox fairness tab to inspect the local before/after verdict."
            elif action_key == "publish_piu_price":
                status = action_meta.get("status") or ("READY" if self.loaded else "NOT LOADED")
                evidence = (
                    f"Current CPI is {self.current_cpi_index:.3f}, implying a live PIU price of £{_ledger().piu_price:.6f}."
                    if self.loaded else
                    "Load the sandbox dataset first."
                )
            elif action_key == "publish_mortality_basis":
                status = action_meta.get("status") or ("READY" if self.loaded else "NOT LOADED")
                evidence = (
                    f"Current study credibility is {self.sandbox_mortality_credibility:.1%}; "
                    f"basis version {self.sandbox_mortality_basis_version} keeps only cohort-level multipliers and proof hashes publishable."
                    if self.loaded else
                    "Load the sandbox dataset first."
                )
            elif action_key == "publish_actuarial_method":
                status = action_meta.get("status") or ("READY" if self.loaded else "NOT LOADED")
                evidence = (
                    f"{self.actuarial_method_count} methodology families are ready to publish. "
                    "The chain records method versions and hashes, not the full actuarial engine."
                    if self.loaded else
                    "Load the sandbox dataset first."
                )
            elif action_key == "publish_valuation_snapshot":
                status = action_meta.get("status") or ("READY" if self.loaded else "NOT LOADED")
                evidence = (
                    "Current valuation snapshot includes a parameter-set hash, member snapshot hash, and cohort summary hash."
                    if self.loaded else
                    "Load the sandbox dataset first."
                )
            elif action_key == "publish_actuarial_result_bundle":
                status = action_meta.get("status") or ("READY" if self.loaded else "NOT LOADED")
                evidence = (
                    f"Current result bundle {self.actuarial_result_contract_key[:10]}… ties the published scheme summary back to declared methods and committed inputs."
                    if self.loaded and self.actuarial_result_contract_key else
                    "Load the sandbox dataset first."
                )
            elif action_key == "publish_stress":
                status = action_meta.get("status") or ("LOCAL READY" if self.stress_ran else "READY")
                evidence = (
                    f"Latest local stress pass rate: {self.stress_pass_rate:.1%}."
                    if self.stress_ran else
                    "Run the sandbox stress view to prepare a publishable result."
                )
            elif action_key == "open_retirement":
                status = action_meta.get("status") or ("READY" if self.selected_wallet else "NO MEMBER")
                evidence = (
                    f"Sample member in focus: {self.selected_wallet}."
                    if self.selected_wallet else
                    "Pick a sandbox member first."
                )
            elif action_key == "release_reserve":
                status = action_meta.get("status") or ("READY" if self.stress_ran else "WAITING")
                evidence = (
                    "Use once a stress result shows a shortfall that merits support."
                )
            else:
                status = action_meta.get("status") or ("READY" if self.registry_present else "NO DEPLOYMENT")
                evidence = "Live Sepolia contract is available." if self.registry_present else "No deployment registry is available."

            before_after = ""
            if action_key == "publish_baseline":
                before_after = f"Before: local cohort fairness state only. After: baseline published to {contract}."
            elif action_key == "publish_piu_price":
                before_after = "Before: CPI only exists in the engine. After: the indexed PIU price is published on-chain for contribution minting and retirement conversion."
            elif action_key == "publish_mortality_basis":
                before_after = (
                    "Before: mortality learning only exists inside the actuarial engine. After: the active basis version, credibility score, and study hash are timestamped on chain without exposing private death records."
                )
            elif action_key == "publish_actuarial_method":
                before_after = (
                    "Before: the methodology only exists in code and documents. After: the active actuarial method version is timestamped on-chain with its spec and reference hashes."
                )
            elif action_key == "publish_valuation_snapshot":
                before_after = (
                    "Before: the valuation inputs only exist off-chain. After: the parameter snapshot and input commitments become an immutable audit record."
                )
            elif action_key == "publish_actuarial_result_bundle":
                before_after = (
                    "Before: the actuarial result only exists in the Python output bundle. After: the published result commitment can be tied back to declared methods and committed inputs."
                )
            elif action_key == "submit_proposal":
                before_after = (
                    "Before: proposal is only local. After: on-chain PASS/FAIL becomes independently verifiable."
                )
            elif action_key == "publish_stress":
                before_after = (
                    "Before: stress output is only local. After: the oracle update can be checked on Etherscan."
                )
            elif action_key == "fund_reserve":
                before_after = (
                    "Before: reserve capacity is unchanged. After: BackstopVault balance increases."
                )
            elif action_key == "release_reserve":
                before_after = (
                    "Before: reserve stays parked. After: reserve capital is released into the protocol."
                )
            elif action_key == "open_retirement":
                before_after = (
                    "Before: member is still in accumulation. After: retirement routing and benefit flow are opened."
                )
            elif action_key == "demo_members":
                before_after = "Before: empty sandbox. After: deterministic members and cohorts are visible for inspection."
            elif action_key == "demo_contributions":
                before_after = "Before: no deterministic history. After: contribution history exists for valuation and fairness checks."

            rows.append(
                {
                    "key": action_key,
                    "title": spec["title"],
                    "summary": spec["summary"],
                    "contract_function": f"{contract}.{spec['function']}",
                    "live_label": (
                        "AFTER NEXT DEPLOYMENT"
                        if action_key in {
                            "publish_mortality_basis",
                            "publish_actuarial_method",
                            "publish_valuation_snapshot",
                            "publish_actuarial_result_bundle",
                        } and not registry_row.get("address")
                        else "LIVE ON SEPOLIA" if live else "LOCAL SANDBOX ONLY"
                    ),
                    "is_live": "yes" if live else "no",
                    "status": status,
                    "latest_tx_hash": tx_hash,
                    "latest_tx_short": short_address(tx_hash) if tx_hash else "—",
                    "tx_url": etherscan_tx(self.wallet_chain_id or self.registry_chain_id, tx_hash) if tx_hash else "",
                    "contract_url": registry_row.get("explorer_url", ""),
                    "address_short": registry_row.get("short", "—"),
                    "verified": registry_row.get("verified", "no"),
                    "evidence": evidence,
                    "before_after": before_after,
                    "estimated_cost_label": str(gas_meta.get("estimated_cost_label", "—")),
                    "estimated_gas_label": str(gas_meta.get("estimated_gas_label", "—")),
                    "count_label": str(gas_meta.get("count", "—")),
                    "actual_cost_label": _compact_currency(float(action_meta.get("fee_gbp", 0.0))) if action_meta.get("fee_wei") else "No signed fee yet",
                    "actual_gas_label": f"{int(action_meta.get('gas_used', 0)):,} gas" if action_meta.get("gas_used") else "Receipt pending",
                    "cost_note": str(gas_meta.get("note", "")),
                }
            )
        self.sandbox_action_rows = rows

    # ======================================================================
    # Derived computed vars for KPI pill coloring
    # ======================================================================
    @rx.var
    def mwr_pill(self) -> str:
        if not self.loaded:
            return "muted"
        if self.mwr >= 0.98:
            return "good"
        if self.mwr >= 0.90:
            return "warn"
        return "bad"

    @rx.var
    def gini_pill(self) -> str:
        if self.cohorts_count < 2:
            return "muted"
        if self.gini <= 0.05:
            return "good"
        if self.gini <= 0.15:
            return "warn"
        return "bad"

    @rx.var
    def intergen_pill(self) -> str:
        if self.cohorts_count < 2:
            return "muted"
        if self.intergen >= 0.95:
            return "good"
        if self.intergen >= 0.80:
            return "warn"
        return "bad"

    @rx.var
    def mwr_fmt(self) -> str:
        return f"{self.mwr:.2f}" if self.loaded else "—"

    @rx.var
    def gini_fmt(self) -> str:
        return f"{self.gini:.3f}" if self.cohorts_count >= 2 else "—"

    @rx.var
    def intergen_fmt(self) -> str:
        return f"{self.intergen:.3f}" if self.cohorts_count >= 2 else "—"

    @rx.var
    def funded_ratio_fmt(self) -> str:
        return f"{self.funded_ratio:.1%}" if self.loaded else "—"

    @rx.var
    def epv_c_fmt(self) -> str:
        return f"{self.epv_c:,.0f}" if self.loaded else "—"

    @rx.var
    def epv_b_fmt(self) -> str:
        return f"{self.epv_b:,.0f}" if self.loaded else "—"

    @rx.var
    def mwr_range_fmt(self) -> str:
        if self.cohorts_count < 2:
            return "—"
        return f"{self.mwr_min:.2f} → {self.mwr_max:.2f}"

    # ---- stress formatters ---------------------------------------------
    @rx.var
    def stress_mean_gini_fmt(self) -> str:
        return f"{self.stress_mean_gini:.3f}" if self.stress_ran else "—"

    @rx.var
    def stress_p95_gini_fmt(self) -> str:
        return f"{self.stress_p95_gini:.3f}" if self.stress_ran else "—"

    @rx.var
    def stress_mean_index_fmt(self) -> str:
        return f"{self.stress_mean_index:.3f}" if self.stress_ran else "—"

    @rx.var
    def stress_p05_index_fmt(self) -> str:
        return f"{self.stress_p05_index:.3f}" if self.stress_ran else "—"

    @rx.var
    def stress_pass_rate_fmt(self) -> str:
        return f"{self.stress_pass_rate:.1%}" if self.stress_ran else "—"

    @rx.var
    def stress_youngest_rate_fmt(self) -> str:
        return f"{self.stress_youngest_rate:.1%}" if self.stress_ran else "—"

    @rx.var
    def stress_pass_pill(self) -> str:
        if not self.stress_ran:
            return "muted"
        if self.stress_pass_rate >= 0.90:
            return "good"
        if self.stress_pass_rate >= 0.70:
            return "warn"
        return "bad"

    @rx.var
    def stress_youngest_pill(self) -> str:
        if not self.stress_ran:
            return "muted"
        if self.stress_youngest_rate <= 0.05:
            return "good"
        if self.stress_youngest_rate <= 0.20:
            return "warn"
        return "bad"

    # ---- selected-member / profile formatters --------------------------
    @rx.var
    def member_age_fmt(self) -> str:
        return f"{self.member_age} yrs" if self.loaded and self.member_age > 0 else "—"

    @rx.var
    def member_first_benefit_fmt(self) -> str:
        if not self.loaded or self.member_first_benefit <= 0:
            return "—"
        return f"£{self.member_first_benefit:,.0f}/yr"

    @rx.var
    def member_fund_peak_fmt(self) -> str:
        if not self.loaded or self.member_fund_peak <= 0:
            return "—"
        return f"£{self.member_fund_peak:,.0f}"

    @rx.var
    def mwr_std_fmt(self) -> str:
        if self.cohorts_count < 2:
            return "—"
        return f"{self.mwr_std:.3f}"

    # ---- twin formatters ------------------------------------------------
    @rx.var
    def twin_peak_nav_fmt(self) -> str:
        return f"£{self.twin_peak_nav:,.0f}" if self.twin_ran else "—"

    @rx.var
    def twin_final_reserve_fmt(self) -> str:
        return f"£{self.twin_final_reserve:,.0f}" if self.twin_ran else "—"

    @rx.var
    def twin_total_contrib_fmt(self) -> str:
        return f"£{self.twin_total_contrib:,.0f}" if self.twin_ran else "—"

    @rx.var
    def twin_total_benefit_fmt(self) -> str:
        return f"£{self.twin_total_benefit:,.0f}" if self.twin_ran else "—"

    @rx.var
    def twin_final_funded_ratio_fmt(self) -> str:
        return f"{self.twin_final_funded_ratio:.1%}" if self.twin_ran else "—"

    @rx.var
    def twin_avg_gini_fmt(self) -> str:
        return f"{self.twin_avg_gini:.3f}" if self.twin_ran else "—"

    @rx.var
    def twin_avg_intergen_fmt(self) -> str:
        return f"{self.twin_avg_intergen:.3f}" if self.twin_ran else "—"

    @rx.var
    def twin_peak_nav_year_fmt(self) -> str:
        return f"@ {self.twin_peak_nav_year}" if self.twin_ran else ""

    @rx.var
    def twin_gini_pill(self) -> str:
        if not self.twin_ran:
            return "muted"
        if self.twin_avg_gini <= 0.05:
            return "good"
        if self.twin_avg_gini <= 0.15:
            return "warn"
        return "bad"

    @rx.var
    def twin_funded_pill(self) -> str:
        if not self.twin_ran:
            return "muted"
        if self.twin_final_funded_ratio >= 0.95:
            return "good"
        if self.twin_final_funded_ratio >= 0.80:
            return "warn"
        return "bad"

    # ---- twin v2 formatters ---------------------------------------------
    @rx.var
    def twin_v2_population_fmt(self) -> str:
        return _compact_number(self.twin_v2_final_population) if self.twin_v2_ran else "—"

    @rx.var
    def twin_v2_active_mix_fmt(self) -> str:
        if not self.twin_v2_ran:
            return "—"
        return (
            f"{_compact_number(self.twin_v2_final_active)} active · "
            f"{_compact_number(self.twin_v2_final_retired)} retired"
        )

    @rx.var
    def twin_v2_nav_fmt(self) -> str:
        return _compact_currency(self.twin_v2_final_nav) if self.twin_v2_ran else "—"

    @rx.var
    def twin_v2_reserve_fmt(self) -> str:
        return _compact_currency(self.twin_v2_final_reserve) if self.twin_v2_ran else "—"

    @rx.var
    def twin_v2_cpi_fmt(self) -> str:
        return f"{self.twin_v2_final_cpi_index:.1f}" if self.twin_v2_ran else "—"

    @rx.var
    def twin_v2_piu_price_fmt(self) -> str:
        return f"£{self.twin_v2_final_piu_price:.3f}" if self.twin_v2_ran else "—"

    @rx.var
    def twin_v2_indexed_liability_fmt(self) -> str:
        return _compact_currency(self.twin_v2_final_indexed_liability) if self.twin_v2_ran else "—"

    @rx.var
    def twin_v2_pius_per_1000_fmt(self) -> str:
        return f"{self.twin_v2_final_pius_per_1000:.0f}" if self.twin_v2_ran else "—"

    @rx.var
    def twin_v2_accrued_pius_fmt(self) -> str:
        return _compact_number(self.twin_v2_final_accrued_pius) if self.twin_v2_ran else "—"

    @rx.var
    def twin_v2_pension_units_fmt(self) -> str:
        return _compact_number(self.twin_v2_final_pension_units) if self.twin_v2_ran else "—"

    @rx.var
    def twin_v2_funded_ratio_fmt(self) -> str:
        return f"{self.twin_v2_final_funded_ratio:.1%}" if self.twin_v2_ran else "—"

    @rx.var
    def twin_v2_average_gini_fmt(self) -> str:
        return f"{self.twin_v2_average_gini:.3f}" if self.twin_v2_ran else "—"

    @rx.var
    def twin_v2_average_stress_fmt(self) -> str:
        return f"{self.twin_v2_average_stress_pass:.1%}" if self.twin_v2_ran else "—"

    @rx.var
    def twin_v2_average_age_fmt(self) -> str:
        return f"{self.twin_v2_average_age:.1f} yrs" if self.twin_v2_ran else "—"

    @rx.var
    def twin_v2_average_salary_fmt(self) -> str:
        return _compact_currency(self.twin_v2_average_salary) if self.twin_v2_ran else "—"

    @rx.var
    def twin_v2_event_count_fmt(self) -> str:
        return _compact_number(self.twin_v2_event_count) if self.twin_v2_ran else "—"

    @rx.var
    def twin_v2_proposal_count_fmt(self) -> str:
        return _compact_number(self.twin_v2_proposal_count) if self.twin_v2_ran else "—"

    @rx.var
    def twin_v2_fairness_pill(self) -> str:
        if not self.twin_v2_ran:
            return "muted"
        if self.twin_v2_average_gini <= 0.06 and self.twin_v2_average_stress_pass >= 0.80:
            return "good"
        if self.twin_v2_average_gini <= 0.12 and self.twin_v2_average_stress_pass >= 0.55:
            return "warn"
        return "bad"

    @rx.var
    def twin_v2_funded_pill(self) -> str:
        if not self.twin_v2_ran:
            return "muted"
        if self.twin_v2_final_funded_ratio >= 0.90:
            return "good"
        if self.twin_v2_final_funded_ratio >= 0.75:
            return "warn"
        return "bad"

    @rx.var
    def current_cpi_fmt(self) -> str:
        return f"{self.current_cpi_index:.3f}"

    @rx.var
    def current_piu_price_fmt(self) -> str:
        return f"£{self.current_piu_price_value:.6f}"

    @rx.var
    def current_pius_per_1000_fmt(self) -> str:
        return f"{1000.0 / max(self.current_piu_price_value, 1e-9):.0f}"

    @rx.var
    def expected_inflation_fmt(self) -> str:
        return f"{self.expected_inflation:.1%}"

    @rx.var
    def gas_network_label(self) -> str:
        return next(
            (row["label"] for row in self.gas_network_rows if row["key"] == self.gas_network_preset),
            self.gas_network_preset.replace("_", " ").title(),
        )

    @rx.var
    def actual_fee_total_fmt(self) -> str:
        return _compact_currency(self.actual_fee_total_gbp) if self.actual_fee_tx_count else "No confirmed fees yet"

    @rx.var
    def last_tx_fee_fmt(self) -> str:
        return _compact_currency(self.last_tx_fee_gbp) if self.last_tx_fee_gbp > 0 else "Waiting for receipt"

    @rx.var
    def sandbox_gas_total_fmt(self) -> str:
        return _compact_currency(self.sandbox_gas_total_cost) if self.sandbox_gas_total_cost > 0 else "—"

    @rx.var
    def investment_wallet_weight_fmt(self) -> str:
        return f"{self.investment_wallet_weight_share:.2%}" if self.investment_wallet_eligible else "Not eligible"

    @rx.var
    def investment_winner_status_label(self) -> str:
        if not self.investment_winner_name:
            return "No ballot draft"
        return "Passes guardrails" if self.investment_winner_passes else "Blocked by guardrails"

    @rx.var
    def investment_winner_status_pill(self) -> str:
        if not self.investment_winner_name:
            return "muted"
        return "good" if self.investment_winner_passes else "bad"

    @rx.var
    def twin_v2_gas_total_fmt(self) -> str:
        return _compact_currency(self.twin_v2_gas_total_cost) if self.twin_v2_gas_total_cost > 0 else "—"

    @rx.var
    def twin_v2_gas_latest_year_fmt(self) -> str:
        return _compact_currency(self.twin_v2_gas_latest_year_cost) if self.twin_v2_gas_latest_year_cost > 0 else "—"

    @rx.var
    def twin_v2_gas_per_member_fmt(self) -> str:
        return f"£{self.twin_v2_gas_latest_cost_per_member:,.2f}" if self.twin_v2_gas_latest_cost_per_member > 0 else "—"

    @rx.var
    def twin_v2_gas_per_1000_fmt(self) -> str:
        return _compact_currency(self.twin_v2_gas_latest_cost_per_1000) if self.twin_v2_gas_latest_cost_per_1000 > 0 else "—"

    @rx.var
    def twin_v2_gas_share_fmt(self) -> str:
        return f"{self.twin_v2_gas_total_share_contributions:.2%}" if self.twin_v2_gas_total_share_contributions > 0 else "—"

    @rx.var
    def twin_v2_gas_pill(self) -> str:
        if not self.twin_v2_ran:
            return "muted"
        if self.gas_network_preset == "ethereum" and (
            self.twin_v2_gas_total_share_contributions >= 0.02
            or self.twin_v2_gas_latest_cost_per_member >= 5.0
        ):
            return "bad"
        if self.twin_v2_gas_total_share_contributions >= 0.008:
            return "warn"
        return "good"

    @rx.var
    def sandbox_mortality_study_hash_short(self) -> str:
        if not self.sandbox_mortality_study_hash:
            return "No study hash yet"
        return self.sandbox_mortality_study_hash[:18] + "…"

    @rx.var
    def twin_v2_mortality_study_hash_short(self) -> str:
        if not self.twin_v2_mortality_study_hash:
            return "No study hash yet"
        return self.twin_v2_mortality_study_hash[:18] + "…"

    # ---- wallet / on-chain computed vars ---------------------------------
    def _contract_is_deployed(self, contract_name: str) -> bool:
        return any(str(row.get("name", "")) == contract_name for row in self.registry_rows)

    @rx.var
    def mortality_basis_contract_deployed(self) -> bool:
        return self._contract_is_deployed("MortalityBasisOracle")

    @rx.var
    def mortality_basis_mode_label(self) -> str:
        return "LIVE ON SEPOLIA" if self.mortality_basis_contract_deployed else "AFTER NEXT DEPLOYMENT"

    @rx.var
    def actuarial_method_contract_deployed(self) -> bool:
        return self._contract_is_deployed("ActuarialMethodRegistry")

    @rx.var
    def actuarial_method_mode_label(self) -> str:
        return "LIVE ON SEPOLIA" if self.actuarial_method_contract_deployed else "AFTER NEXT DEPLOYMENT"

    @rx.var
    def actuarial_result_contract_deployed(self) -> bool:
        return self._contract_is_deployed("ActuarialResultRegistry")

    @rx.var
    def actuarial_result_mode_label(self) -> str:
        return "LIVE ON SEPOLIA" if self.actuarial_result_contract_deployed else "AFTER NEXT DEPLOYMENT"

    @rx.var
    def wallet_pill(self) -> str:
        if not self.wallet_connected:
            return "muted"
        if self.wallet_is_sepolia:
            return "good"
        return "warn"

    @rx.var
    def wallet_pill_label(self) -> str:
        if not self.wallet_connected:
            return "NOT CONNECTED"
        if self.wallet_is_sepolia:
            return "SEPOLIA"
        return "WRONG NETWORK"

    @rx.var
    def deployment_pill(self) -> str:
        if not self.registry_present:
            return "muted"
        if self.registry_on_sepolia and self.registry_verified:
            return "good"
        if self.registry_on_sepolia:
            return "warn"
        return "muted"

    @rx.var
    def deployment_pill_label(self) -> str:
        if not self.registry_present:
            return "NO DEPLOYMENT"
        if self.registry_on_sepolia and self.registry_verified:
            return "VERIFIED · SEPOLIA"
        if self.registry_on_sepolia:
            return "DEPLOYED · SEPOLIA"
        return f"DEPLOYED · {self.registry_chain_name}".upper()

    @rx.var
    def devtools_status_pill(self) -> str:
        return {
            "idle": "muted",
            "running": "warn",
            "success": "good",
            "failed": "bad",
        }.get(self.devtools_status, "muted")

    @rx.var
    def devtools_status_label(self) -> str:
        return {
            "idle": "IDLE",
            "running": "RUNNING",
            "success": "SUCCESS",
            "failed": "FAILED",
        }.get(self.devtools_status, "IDLE")

    @rx.var
    def devtools_log_snippet(self) -> str:
        if not self.devtools_logs:
            return "No command output yet."
        return self.devtools_logs[:600] + ("…" if len(self.devtools_logs) > 600 else "")

    @rx.var
    def tx_pill(self) -> str:
        return {
            "idle":      "muted",
            "pending":   "warn",
            "confirmed": "good",
            "failed":    "bad",
        }.get(self.last_tx_status, "muted")

    @rx.var
    def tx_pill_label(self) -> str:
        return {
            "idle":      "NO RECENT ACTION",
            "pending":   "PENDING",
            "confirmed": "CONFIRMED",
            "failed":    "FAILED",
        }.get(self.last_tx_status, "IDLE")

    @rx.var
    def registry_explorer_deployer_url(self) -> str:
        if not self.registry_deployer or not self.registry_chain_id:
            return ""
        return etherscan_address(
            self.registry_chain_id, self.registry_deployer
        ) or ""

    @rx.var
    def wallet_explorer_url(self) -> str:
        if not self.wallet_address or not self.wallet_chain_id:
            return ""
        return etherscan_address(
            self.wallet_chain_id, self.wallet_address
        ) or ""

    @rx.var
    def can_run_live_action(self) -> bool:
        return (
            self.wallet_connected
            and self.wallet_is_sepolia
            and self.registry_present
            and self.confirm_target_addr != ""
        )

    @rx.var
    def live_action_blocker(self) -> str:
        """Plain-English reason a live action is unavailable, or ''."""
        if not self.wallet_connected:
            return "Connect your wallet to sign live actions."
        if not self.wallet_is_sepolia:
            return "Switch your wallet to the Sepolia test network."
        if not self.registry_present:
            return (
                "No deployment registered yet — run the deploy script and fill "
                "contracts/deployments/sepolia.json."
            )
        if self.confirm_target_addr == "":
            return (
                "This action needs a deployed contract address in the Sepolia registry. "
                "MortalityBasisOracle is defined in the repo but is not deployed on the current Sepolia registry yet."
            )
        return ""
