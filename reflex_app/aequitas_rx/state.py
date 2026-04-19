"""Reactive state for the Aequitas Reflex frontend.

This module is the only place in the Reflex app that touches the Python
actuarial engine. Every engine call funnels through the service helpers
below, and `AppState` holds only picklable derived data (lists, dicts,
scalars) so Reflex can hydrate it cleanly per page load.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

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
from engine.seed import seed_ledger  # noqa: E402


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

    # ======================================================================
    # Internals — recompute derived state
    # ======================================================================
    def _refresh(self):
        led = _ledger()

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
