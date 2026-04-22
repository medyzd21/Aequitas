"""Reactive state for the Aequitas Reflex frontend.

This module is the only place in the Reflex app that touches the Python
actuarial engine. Every engine call funnels through the service helpers
below, and `AppState` holds only picklable derived data (lists, dicts,
scalars) so Reflex can hydrate it cleanly per page load.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, ClassVar

import reflex as rx

# --------------------------------------------------------------------------- path
# Make the repo root importable so the engine modules can be reused.
# repo_root / reflex_app / aequitas_rx / state.py  →  repo_root is parents[2]
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# --------------------------------------------------------------------------- engine
from engine import actuarial as act  # noqa: E402
from engine.chain_bridge import (  # noqa: E402
    calls_to_json,
    encode_backstop_deposit,
    encode_backstop_release,
    encode_baseline,
    encode_open_retirement,
    encode_pool_deposit,
    encode_proposal,
    encode_stress_update,
    ledger_to_chain_calls,
)
from engine.chain_stub import EventLog  # noqa: E402
from engine.deployments import load_latest  # noqa: E402
from engine.onchain_registry import (  # noqa: E402
    LOCAL_ANVIL_CHAIN_ID,
    SEPOLIA_CHAIN_ID,
    chain_name as _chain_name,
    etherscan_address,
    etherscan_tx,
    is_sepolia as _is_sepolia,
    load_any_deployment,
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
from engine.ledger import CohortLedger  # noqa: E402
from engine.models import Proposal  # noqa: E402
from engine.projection import project_fund, project_member  # noqa: E402
from engine.scenarios import get_preset, list_presets  # noqa: E402
from engine.seed import seed_ledger  # noqa: E402
from engine.system_simulation import run_system_simulation  # noqa: E402


# --------------------------------------------------------------------------- service layer
# A single ledger + event log instance lives at module scope — Phase 1 is a
# single-user demo. Phase 2 will move to per-session state.
_LEDGER: CohortLedger | None = None
_EVENT_LOG: EventLog | None = None


def _ledger() -> CohortLedger:
    global _LEDGER
    if _LEDGER is None:
        _LEDGER = CohortLedger(piu_price=1.0)
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
    return f"{t}"


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

    # ---- deployment ribbon ---------------------------------------------
    deployment_detected: bool = False
    deployment_owner: str = ""
    deployment_count: int = 0
    deployment_address_rows: list[dict] = []

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
    last_tx_contract:      str = ""    # e.g. "FairnessGate"
    last_tx_function:      str = ""    # e.g. "submitAndEvaluate"
    last_tx_explorer_url:  str = ""
    last_tx_error:         str = ""

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
    stress_update_payload: dict = {}
    backstop_deposit_payload: dict = {}
    backstop_release_payload: dict = {}

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

    # ======================================================================
    # Event handlers
    # ======================================================================
    def refresh_view(self):
        """Called on every page load — keeps state fresh across navigation.

        Not named `hydrate` because recent Reflex versions reserve that
        identifier for internal client-state sync.
        """
        self._refresh()

    def load_demo(self):
        """Seed the 15-member demo dataset."""
        global _LEDGER
        _LEDGER = seed_ledger(CohortLedger(
            piu_price=1.0,
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
        _LEDGER = CohortLedger(piu_price=1.0)
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
        else:
            self.wallet_connected = False
            self.wallet_last_error = str(r.get("error") or "Connection cancelled")
            self.wallet_status_message = "Wallet not connected"

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
            "window.__aequitasLastConfirmedTx || ''",
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
        txh = str(result or "").strip().lower()
        if not txh or txh != (self.last_tx_hash or "").lower():
            return
        if self.last_tx_status == "confirmed":
            return
        self.last_tx_status = "confirmed"
        self.last_tx_error = ""
        _event_log().append(
            "tx_confirmed",
            action=self.last_tx_action,
            hash=txh,
            status=self.last_tx_status,
        )
        self._refresh_events()

    def disconnect_wallet(self):
        """Local-only disconnect — MetaMask has no revoke API."""
        self.wallet_connected = False
        self.wallet_address = ""
        self.wallet_short = ""
        self.wallet_chain_id = 0
        self.wallet_chain_name = ""
        self.wallet_is_sepolia = False
        self.wallet_status_message = "Wallet not connected"

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
        if self.confirm_target_addr:
            self.confirm_params_rows.append(
                {"key": "Deployed at", "value": self.confirm_target_addr}
            )

    def close_action(self):
        self.confirm_open = False

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
        self.last_tx_action    = spec["label"]
        self.last_tx_contract  = spec["contract"]
        self.last_tx_function  = spec["function"]
        self.last_tx_error     = ""

        _event_log().append(
            "action_confirmed",
            action=self.confirm_action_key,
            label=spec["label"],
            contract=spec["contract"],
            function=spec["function"],
            mode=spec["mode"],
        )

        if not spec.get("live"):
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
        self.confirm_open = False
        # We pass the chosen action via the JS call so the bridge can map it
        # to the right ABI + argument set. All heavy lifting lives in JS.
        inner = (
            f"window.aequitasWallet.runAction('{self.confirm_action_key}', "
            f"{{contract:'{key}', address:'{addr}', func:'{fn}'}})"
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
            self.last_tx_hash  = txh
            self.last_tx_short = short_address(txh)
            self.last_tx_status = "confirmed" if r.get("confirmed") else "pending"
            self.last_tx_explorer_url = etherscan_tx(
                self.wallet_chain_id or SEPOLIA_CHAIN_ID, txh
            ) or ""
            _event_log().append(
                "tx_submitted",
                action=self.confirm_action_key,
                hash=txh,
                status=self.last_tx_status,
            )
            self._refresh_events()
        else:
            self.last_tx_status = "failed"
            self.last_tx_error  = str(r.get("error") or "Transaction rejected")
            _event_log().append(
                "tx_failed",
                action=self.confirm_action_key,
                error=self.last_tx_error,
            )
            self._refresh_events()

    def clear_last_tx(self):
        self.last_tx_status = "idle"
        self.last_tx_hash = ""
        self.last_tx_short = ""
        self.last_tx_action = ""
        self.last_tx_contract = ""
        self.last_tx_function = ""
        self.last_tx_explorer_url = ""
        self.last_tx_error = ""

    # ======================================================================
    # Internals — recompute derived state
    # ======================================================================
    def _refresh_registry(self):
        """Hydrate fields from the on-chain registry (sepolia.json)."""
        reg = load_any_deployment()
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

        # richer on-chain registry (sepolia.json, or fallback legacy)
        self._refresh_registry()

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
            }
            for m in led
        ]
        self.valuation_rows = [
            {
                "wallet": v.wallet,
                "epv_contributions": round(float(v.epv_contributions), 0),
                "epv_benefits":      round(float(v.epv_benefits), 0),
                "money_worth_ratio": round(float(v.money_worth_ratio), 3),
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
            horizon=60,
        )
        if not fund_df.empty:
            cols = ["year", "fund_value", "contributions", "benefit_payments"]
            self.fund_projection_rows = [
                {k: (int(v) if k == "year" else float(v)) for k, v in row.items()}
                for row in fund_df[cols].to_dict("records")
            ]

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
            horizon=60,
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
        cols = ["year", "fund_value", "contribution", "benefit_payment"]
        self.member_projection_rows = [
            {k: (int(v) if k == "year" else float(v)) for k, v in row.items()}
            for row in df[cols].to_dict("records")
        ]

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

    def _refresh_payloads(self):
        led = _ledger()
        if len(led) == 0:
            self.ledger_payload_preview = []
            self.baseline_payload = {}
            self.proposal_payload = {}
            self.pool_deposit_payload = {}
            self.open_retirement_payload = {}
            self.stress_update_payload = {}
            self.backstop_deposit_payload = {}
            self.backstop_release_payload = {}
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
        self.stress_update_payload = encode_stress_update(
            0.25, "p95_gini>threshold", str({"n_cohorts": len(cv)})
        ).as_dict()
        self.backstop_deposit_payload = encode_backstop_deposit(5.0).as_dict()
        self.backstop_release_payload = encode_backstop_release(1.0).as_dict()

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

    # ---- wallet / on-chain computed vars ---------------------------------
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
        return ""
