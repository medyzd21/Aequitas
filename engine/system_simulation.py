"""Digital-twin system simulator — the heart of the Aequitas demo.

Takes a `SystemConfig` (see `engine.scenarios`) and runs the scheme
year-by-year for `horizon_years`. Every year:

  1. New joiners enter (Poisson with `EntrantConfig.mean_per_year`).
  2. Every active member contributes `contribution_rate · salary`.
  3. Salaries grow by `salary_growth` (± scenario perturbation).
  4. Fund NAV earns a stochastic log-normal return (with optional
     scheduled shocks like MARKET_CRASH applied once).
  5. Members who reach retirement_age flip to "retired" and their
     annuity is locked at that point.
  6. Mortality: a Bernoulli draw per active/retired member using the
     Gompertz-Makeham table (optionally scaled by scheduled
     MORTALITY_SPIKE events for one year).
  7. Benefit payments are made to retirees (level annuity, optionally
     indexed to inflation).
  8. Every `stress_every_years`, run `stochastic_cohort_stress` on the
     live ledger's cohort valuation and publish a SimEvent.
  9. If the stress result breaches `backstop_release_threshold`, release
     up to the benefit shortfall from BackstopVault.
 10. Pre-scheduled proposals are evaluated at their offset and routed
     through `evaluate_proposal`.

At each year-end, a row of aggregate KPIs is written to
`SystemResult.annual` (population split, fund NAV, funded ratio, Gini,
intergen index, corridor failures, backstop state, MWR by cohort).

Reuses everything already shipped:
    engine.actuarial        default_table, annuity_rate
    engine.ledger.CohortLedger   register_member / contribute /
                                 cohort_valuation / value_all
    engine.fairness         evaluate_proposal / mwr_gini /
                            intergenerational_index
    engine.fairness_stress  stochastic_cohort_stress / build_cohort_betas

Perf note
---------
10k members × 40 years × 800 stress scenarios runs in a few seconds
on a laptop. The hot path is a NumPy-vectorised Bernoulli survival
draw, plus one pandas call per year for cohort aggregation.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any, Iterable

import numpy as np
import pandas as pd

from engine import actuarial as act
from engine.events import (
    BACKSTOP_DEPOSIT, BACKSTOP_RELEASE, CONTRACT_MAP, CONTRIBUTION,
    DEATH, INFLATION_SHOCK, INVESTMENT_RETURN, JOIN, MARKET_CRASH,
    MORTALITY_SPIKE, PROPOSAL, RETIREMENT, SimEvent, STRESS_RUN,
    YEAR_CLOSED,
)
from engine.fairness import (
    evaluate_proposal, intergenerational_index, mwr_gini,
)
from engine.fairness_stress import (
    build_cohort_betas, stochastic_cohort_stress,
)
from engine.ledger import CohortLedger
from engine.models import Member
from engine.population import draw_entrants, generate_population
from engine.scenarios import (
    ScheduledProposal, ScheduledShock, SystemConfig,
)


# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------

@dataclass
class SystemResult:
    """Everything the simulator produces."""
    config:           SystemConfig
    annual:           pd.DataFrame                 # one row per year (KPIs)
    cohort_mwr_long:  pd.DataFrame                 # long form: year × cohort → mwr
    representative:   pd.DataFrame                 # long form: year × profile → state
    events:           list[SimEvent]               # timeline events
    final_members:    int = 0
    final_retirees:   int = 0
    final_deceased:   int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "config_name":   self.config.name,
            "annual":        self.annual.to_dict("records"),
            "cohort_mwr":    self.cohort_mwr_long.to_dict("records"),
            "representative": self.representative.to_dict("records"),
            "events":        [e.to_dict() for e in self.events],
            "final_members":  self.final_members,
            "final_retirees": self.final_retirees,
            "final_deceased": self.final_deceased,
        }


# ---------------------------------------------------------------------------
# Internal per-member state (kept lightweight — Member stays as the
# ledger-visible truth, this dict tracks the bits we mutate year on year)
# ---------------------------------------------------------------------------

_STATUS_ACTIVE  = "active"
_STATUS_RETIRED = "retired"
_STATUS_DECEASED = "deceased"


def _pick_representatives(members: list[Member], year: int) -> dict[str, str]:
    """Return one wallet per representative profile.

    Used purely for the 'representative stories' panel — picks four
    lifecycle archetypes from the live roster so the UI can chart their
    fund trajectory through time.
    """
    if not members:
        return {}
    actives = [(m, year - m.birth_year) for m in members]
    youngest = min(actives, key=lambda t: t[1])[0].wallet
    oldest   = max(actives, key=lambda t: t[1])[0].wallet
    near_candidates = [t for t in actives if t[1] < t[0].retirement_age]
    near = (max(near_candidates, key=lambda t: t[1])[0].wallet
            if near_candidates else oldest)
    ages = sorted(t[1] for t in actives)
    median = ages[len(ages) // 2]
    mid = min(actives, key=lambda t: abs(t[1] - median))[0].wallet
    return {
        "young":   youngest,
        "mid":     mid,
        "near":    near,
        "retiree": oldest,
    }


def _bernoulli_death(
    rng: np.random.Generator,
    ages: np.ndarray,
    sex_loadings: np.ndarray,
    mortality_mult: float,
    gm: act.GompertzMakeham,
) -> np.ndarray:
    """Return a boolean mask of members who die this year.

    Gompertz–Makeham one-year death probability at age x is
    q_x = 1 − exp(−μ(x+0.5)). We multiply μ by `mortality_mult` (for
    scheduled mortality spikes) and by each member's `sex_loadings`.
    """
    mu = gm.A + gm.B * (gm.c ** (ages.astype(float) + 0.5))
    q  = 1.0 - np.exp(-mortality_mult * sex_loadings * mu)
    draws = rng.random(size=ages.shape[0])
    return draws < q


def _log_normal_return(
    rng: np.random.Generator,
    mean: float,
    vol:  float,
) -> float:
    """Scalar log-normal annual return."""
    log_mu = np.log((1 + mean) ** 2 / np.sqrt((1 + mean) ** 2 + vol ** 2))
    log_sd = np.sqrt(np.log(1 + vol ** 2 / (1 + mean) ** 2))
    return float(rng.lognormal(mean=log_mu, sigma=log_sd)) - 1.0


# ---------------------------------------------------------------------------
# Main entry
# ---------------------------------------------------------------------------

def run_system_simulation(cfg: SystemConfig) -> SystemResult:
    """Run the digital-twin simulation end-to-end.

    Parameters
    ----------
    cfg : SystemConfig from engine.scenarios.

    Returns
    -------
    SystemResult with annual KPIs, cohort MWR history, representative-
    member traces, and the event timeline.
    """
    rng = np.random.default_rng(int(cfg.seed))
    gm = act.GompertzMakeham()

    # Build the initial roster via the population generator and
    # ingest into a fresh CohortLedger.
    initial = generate_population(
        cfg.n_members,
        start_year=cfg.start_year,
        seed=int(cfg.seed),
        cfg=cfg.pop_cfg,
    )
    ledger = CohortLedger(
        piu_price=1.0,
        valuation_year=cfg.start_year,
        discount_rate=cfg.discount_rate,
        salary_growth=cfg.salary_growth,
        investment_return=cfg.mean_return,
    )
    for m in initial:
        ledger.members[m.wallet] = m
        ledger.cohort_aggregate_contrib.setdefault(m.cohort, 0.0)

    # Per-member status / fund (we track the fund here because it
    # evolves stochastically year-on-year outside the ledger's
    # actuarial-mean projection).
    status: dict[str, str] = {w: _STATUS_ACTIVE for w in ledger.members}
    fund:   dict[str, float] = {w: 0.0 for w in ledger.members}
    locked_benefit: dict[str, float] = {}

    # Bookkeeping
    reserve = float(cfg.backstop_initial)
    events: list[SimEvent] = []
    annual_rows: list[dict[str, Any]] = []
    cohort_long_rows: list[dict[str, Any]] = []
    rep_rows: list[dict[str, Any]] = []

    # Precompute scheduled shock / proposal lookup tables
    shocks_by_year:    dict[int, list[ScheduledShock]]    = {}
    props_by_year:     dict[int, list[ScheduledProposal]] = {}
    for s in cfg.shocks:
        shocks_by_year.setdefault(int(s.offset), []).append(s)
    for p in cfg.proposals:
        props_by_year.setdefault(int(p.offset), []).append(p)

    # Pick representatives up-front so their IDs are stable across years
    reps = _pick_representatives(list(ledger.members.values()),
                                 cfg.start_year)

    # Sex loading for mortality draws: {"M": 1.15, "F": 0.88, "U": 1.0}
    def sex_load(s: str) -> float:
        return {"M": 1.15, "F": 0.88}.get(s, 1.0)

    cum_joiner_offset = 0  # to keep new wallet names unique

    # ---------------------------------------------------------------- loop
    for offset in range(cfg.horizon_years):
        year = int(cfg.start_year) + offset
        ledger.valuation_year = year
        year_events: list[SimEvent] = []

        # 1 -- Entrants ------------------------------------------------
        entrants = draw_entrants(
            rng, year, cfg.entrants,
            wallet_prefix=cfg.pop_cfg.wallet_prefix,
            wallet_offset=cfg.n_members + cum_joiner_offset,
        )
        if entrants:
            for m in entrants:
                if m.wallet in ledger.members:
                    continue
                ledger.members[m.wallet] = m
                ledger.cohort_aggregate_contrib.setdefault(m.cohort, 0.0)
                status[m.wallet] = _STATUS_ACTIVE
                fund[m.wallet] = 0.0
            cum_joiner_offset += len(entrants)
            year_events.append(SimEvent(year, JOIN,
                                        {"count": len(entrants)}))

        # Determine this year's return / shocks --------------------
        base_return = _log_normal_return(rng, cfg.mean_return, cfg.return_vol)
        shocked_return = base_return
        mortality_mult = cfg.mortality_multiplier
        inflation = cfg.inflation
        for sh in shocks_by_year.get(offset, []):
            if sh.kind == MARKET_CRASH:
                # apply drop multiplicatively
                shocked_return = (1.0 + base_return) * (1.0 - float(sh.magnitude)) - 1.0
                year_events.append(SimEvent(year, MARKET_CRASH,
                                            {"drop": float(sh.magnitude)}))
            elif sh.kind == MORTALITY_SPIKE:
                mortality_mult *= float(sh.magnitude)
                year_events.append(SimEvent(year, MORTALITY_SPIKE,
                                            {"multiplier": float(sh.magnitude)}))
            elif sh.kind == INFLATION_SHOCK:
                inflation = float(sh.magnitude)
                year_events.append(SimEvent(year, INFLATION_SHOCK,
                                            {"inflation": inflation}))

        # 2/3 -- Contributions & salary growth ---------------------
        total_contrib = 0.0
        active_wallets: list[str] = []
        for w, st in status.items():
            if st != _STATUS_ACTIVE:
                continue
            m = ledger.members[w]
            age = year - m.birth_year
            if age >= m.retirement_age:
                # handled in step 5 — we'll flip to retired below
                active_wallets.append(w)
                continue
            c = float(m.salary) * float(m.contribution_rate)
            if c > 0:
                m.total_contributions += c
                m.piu_balance += c / ledger.piu_price
                ledger.cohort_aggregate_contrib[m.cohort] = (
                    ledger.cohort_aggregate_contrib.get(m.cohort, 0.0) + c
                )
                fund[w] += c
                total_contrib += c
            # salary growth for next year
            m.salary = float(m.salary) * (1.0 + cfg.salary_growth)
            active_wallets.append(w)
        if total_contrib > 0:
            year_events.append(SimEvent(year, CONTRIBUTION,
                                        {"total": total_contrib}))

        # Route a bps fraction of contributions into the backstop
        auto_deposit = total_contrib * (cfg.backstop_deposit_bps / 10_000.0)
        if auto_deposit > 0:
            reserve += auto_deposit
            year_events.append(SimEvent(year, BACKSTOP_DEPOSIT,
                                        {"amount": auto_deposit}))

        # 4 -- Apply investment return to every fund ---------------
        if fund:
            for w in fund:
                fund[w] *= (1.0 + shocked_return)
            reserve *= (1.0 + shocked_return)
        year_events.append(SimEvent(year, INVESTMENT_RETURN,
                                    {"return": shocked_return}))

        # 5 -- Retirements ------------------------------------------
        retire_count = 0
        for w in list(active_wallets):
            if status[w] != _STATUS_ACTIVE:
                continue
            m = ledger.members[w]
            age = year - m.birth_year
            if age >= m.retirement_age:
                status[w] = _STATUS_RETIRED
                table = act.default_table(m.sex)
                ann_rate = act.annuity_rate(
                    table, int(m.retirement_age), cfg.discount_rate,
                )
                locked_benefit[w] = float(fund[w]) * ann_rate
                retire_count += 1
        if retire_count:
            year_events.append(SimEvent(year, RETIREMENT,
                                        {"count": retire_count}))

        # 6 -- Mortality --------------------------------------------
        alive = [w for w, st in status.items()
                 if st in (_STATUS_ACTIVE, _STATUS_RETIRED)]
        if alive:
            ages = np.array(
                [year - ledger.members[w].birth_year for w in alive],
                dtype=np.int64,
            )
            loads = np.array(
                [sex_load(ledger.members[w].sex) for w in alive],
                dtype=np.float64,
            )
            mask = _bernoulli_death(rng, ages, loads, mortality_mult, gm)
            deaths = [w for w, died in zip(alive, mask) if died]
            for w in deaths:
                status[w] = _STATUS_DECEASED
                # When a retiree dies their remaining fund stays pooled
                # (LongevaPool semantics) — we simply zero their personal
                # benefit but keep the fund contribution to the reserve.
                if w in locked_benefit:
                    reserve += max(0.0, fund[w])
                    fund[w] = 0.0
                    locked_benefit.pop(w, None)
            if deaths:
                year_events.append(SimEvent(year, DEATH,
                                            {"count": len(deaths)}))

        # 7 -- Benefit payments --------------------------------------
        total_benefit = 0.0
        for w, b in list(locked_benefit.items()):
            if status[w] != _STATUS_RETIRED:
                continue
            # Index the locked benefit for inflation each year after
            # retirement (level real, nominal grows at inflation).
            locked_benefit[w] = b * (1.0 + inflation)
            pay = locked_benefit[w]
            if fund[w] >= pay:
                fund[w] -= pay
                total_benefit += pay
            elif reserve + fund[w] >= pay:
                shortfall = pay - fund[w]
                fund[w] = 0.0
                reserve -= shortfall
                total_benefit += pay
                year_events.append(SimEvent(year, BACKSTOP_RELEASE,
                                            {"amount": shortfall}))
            else:
                # Can't fully pay — pay what we can
                partial = max(0.0, fund[w] + max(0.0, reserve))
                fund[w] = 0.0
                reserve = max(0.0, reserve - max(0.0, partial - fund[w]))
                total_benefit += partial

        # 8 -- Stress run (periodic) --------------------------------
        stress_pass_rate = None
        stress_level = 0.0
        if (offset + 1) % max(1, cfg.stress_every_years) == 0:
            try:
                cv = ledger.cohort_valuation()
                if len(cv) >= 2:
                    slope = 0.5
                    if cfg.name == "young_stress":
                        slope = 0.85
                    betas = build_cohort_betas(sorted(cv.keys()), slope=slope)
                    result = stochastic_cohort_stress(
                        cv,
                        n_scenarios=int(cfg.stress_scenarios),
                        factor_sigma=cfg.return_vol,
                        idiosyncratic_sigma=0.03,
                        betas=betas,
                        generational_slope=slope,
                        corridor_delta=cfg.corridor_delta,
                        youngest_poor_threshold=0.90,
                        seed=int(cfg.seed) + offset,
                    )
                    stress_pass_rate = float(result["corridor_pass_rate"])
                    # stress_level ∈ [0,1]: higher if corridor often fails
                    stress_level = float(1.0 - stress_pass_rate)
                    year_events.append(SimEvent(year, STRESS_RUN, {
                        "pass_rate": stress_pass_rate,
                        "mean_gini": float(result["mean_gini"]),
                        "p95_gini":  float(result["p95_gini"]),
                    }))
                    # 9 -- Backstop release if stress breach ---------
                    if (stress_level >= cfg.backstop_release_threshold
                            and reserve > 0):
                        release = min(reserve * 0.10, 100_000.0)
                        if release > 0:
                            reserve -= release
                            year_events.append(SimEvent(year, BACKSTOP_RELEASE,
                                                        {"amount": release}))
            except Exception:
                # A stress failure should not abort the simulation —
                # we swallow and continue (the UI will just see no
                # STRESS_RUN event that year).
                pass

        # 10 -- Scheduled proposals ---------------------------------
        for prop in props_by_year.get(offset, []):
            cv = ledger.cohort_valuation()
            if not cv:
                continue
            cohorts_sorted = sorted(cv.keys())
            # resolve symbolic keys
            mults: dict[int, float] = {int(c): 1.0 for c in cohorts_sorted}
            for key, m in (prop.multipliers or {}).items():
                if key == "YOUNGEST":
                    mults[int(cohorts_sorted[-1])] = float(m)
                elif key == "OLDEST":
                    mults[int(cohorts_sorted[0])] = float(m)
                else:
                    try:
                        mults[int(key)] = float(m)
                    except (ValueError, TypeError):
                        continue
            outcome = evaluate_proposal(cv, mults, delta=cfg.corridor_delta)
            year_events.append(SimEvent(year, PROPOSAL, {
                "name":    prop.name,
                "passes":  bool(outcome.get("passes")),
                "gini_before": float(outcome.get("gini_before", 0.0)),
                "gini_after":  float(outcome.get("gini_after", 0.0)),
            }))

        # ---- Aggregate KPIs at year end --------------------------
        actives_now   = sum(1 for v in status.values() if v == _STATUS_ACTIVE)
        retirees_now  = sum(1 for v in status.values() if v == _STATUS_RETIRED)
        deceased_now  = sum(1 for v in status.values() if v == _STATUS_DECEASED)
        fund_nav = float(sum(fund.values()))

        cv_now = ledger.cohort_valuation() if len(ledger) else {}
        gini_now = float(mwr_gini({c: cv_now[c]["money_worth_ratio"]
                                   for c in cv_now})) if cv_now else 0.0
        index_now = float(intergenerational_index(
            {c: cv_now[c]["money_worth_ratio"] for c in cv_now}
        )) if cv_now else 1.0
        epv_b_now = float(sum(cv_now[c]["epv_benefits"] for c in cv_now))
        epv_c_now = float(sum(cv_now[c]["epv_contributions"] for c in cv_now))
        mwr_now   = (epv_b_now / epv_c_now) if epv_c_now else 0.0
        funded_ratio = (fund_nav + reserve) / (epv_b_now + 1e-9) if epv_b_now else 1.0

        # count deaths this year from the emitted events (single source)
        deaths_count = sum(
            int(e.data.get("count", 0))
            for e in year_events if e.kind == DEATH
        )

        # cohort-wise MWR (long form for heatmap)
        for c, row in cv_now.items():
            cohort_long_rows.append({
                "year":   year,
                "cohort": int(c),
                "mwr":    round(float(row["money_worth_ratio"]), 4),
            })

        # representative traces
        for prof_key, wallet in reps.items():
            if wallet not in ledger.members:
                continue
            m = ledger.members[wallet]
            rep_rows.append({
                "year":          year,
                "profile":       prof_key,
                "wallet":        wallet,
                "status":        status.get(wallet, "deceased"),
                "age":           year - m.birth_year,
                "salary":        round(float(m.salary), 2),
                "fund":          round(float(fund.get(wallet, 0.0)), 2),
                "benefit":       round(float(locked_benefit.get(wallet, 0.0)), 2),
            })

        annual_rows.append({
            "year":            year,
            "active":          actives_now,
            "retired":         retirees_now,
            "deceased":        deceased_now,
            "joined":          len(entrants),
            "retiring":        retire_count,
            "deaths":          int(deaths_count),
            "total_contrib":   round(total_contrib, 2),
            "total_benefit":   round(total_benefit, 2),
            "fund_nav":        round(fund_nav, 2),
            "reserve":         round(reserve, 2),
            "funded_ratio":    round(funded_ratio, 4),
            "mwr_scheme":      round(mwr_now, 4),
            "gini":            round(gini_now, 4),
            "intergen_index":  round(index_now, 4),
            "stress_pass_rate": (round(stress_pass_rate, 4)
                                 if stress_pass_rate is not None else None),
            "return":          round(shocked_return, 4),
        })

        events.extend(year_events)
        events.append(SimEvent(year, YEAR_CLOSED,
                               {"funded_ratio": funded_ratio}))

    # ---- package ----------------------------------------------------
    annual_df = pd.DataFrame(annual_rows)
    cohort_long_df = pd.DataFrame(cohort_long_rows)
    rep_df = pd.DataFrame(rep_rows)

    final_retirees = sum(1 for v in status.values() if v == _STATUS_RETIRED)
    final_deceased = sum(1 for v in status.values() if v == _STATUS_DECEASED)
    final_members  = len(ledger)

    return SystemResult(
        config=cfg,
        annual=annual_df,
        cohort_mwr_long=cohort_long_df,
        representative=rep_df,
        events=events,
        final_members=final_members,
        final_retirees=final_retirees,
        final_deceased=final_deceased,
    )


__all__ = ["SystemResult", "run_system_simulation"]
