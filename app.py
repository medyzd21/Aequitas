"""Aequitas — Streamlit prototype.

Run locally from PyCharm:

    streamlit run app.py

Tabs:

    1. Overview            — scheme KPIs and fund projection
    2. Members             — register, contribute, view roster
    3. Actuarial Valuation — EPVs, MWRs, life-table transparency
    4. Projections         — deterministic year-by-year path per member
    5. Monte Carlo         — distribution of retirement outcomes
    6. Fairness            — MWR dispersion, Gini, MVP corridor demo
    7. Governance Sandbox  — deterministic cohort proposals + audit chain
    8. Fairness Stress     — stochastic cohort-shock stress test
    9. Audit Chain         — append-only hashed log of governance events
   10. Contracts           — preview the on-chain payloads the engine emits
"""
from __future__ import annotations

import math
from pathlib import Path

import pandas as pd
import streamlit as st

from engine import actuarial as act
from engine.chain_bridge import (
    calls_to_json,
    encode_baseline,
    encode_proposal,
    encode_stress_update,
    ledger_to_chain_calls,
)
from engine.chain_stub import EventLog
from engine.models import Proposal
from engine.fairness import (
    evaluate_proposal,
    fairness_corridor_check,
    intergenerational_index,
    mwr_dispersion,
    mwr_gini,
)
from engine.fairness_stress import (
    build_cohort_betas,
    stochastic_cohort_stress,
    summary_frame,
)
from engine.ledger import CohortLedger
from engine.projection import project_fund, project_member
from engine.seed import seed_ledger
from engine.simulation import simulate_fund, simulate_member


st.set_page_config(
    page_title="Aequitas — Actuarial Prototype",
    layout="wide",
    page_icon=":bar_chart:",
)


# --------------------------------------------------------------------------- state
def _init_state() -> None:
    if "ledger" not in st.session_state:
        st.session_state.ledger = CohortLedger(piu_price=1.0)
    if "event_log" not in st.session_state:
        st.session_state.event_log = EventLog()


_init_state()


# --------------------------------------------------------------------------- sidebar
st.sidebar.title("Aequitas controls")

with st.sidebar.expander("Assumptions", expanded=True):
    st.session_state.ledger.valuation_year = st.number_input(
        "Valuation year", min_value=2020, max_value=2060,
        value=int(st.session_state.ledger.valuation_year), step=1,
    )
    st.session_state.ledger.discount_rate = st.slider(
        "Discount rate (risk-free)", 0.0, 0.10,
        float(st.session_state.ledger.discount_rate), 0.005,
    )
    st.session_state.ledger.investment_return = st.slider(
        "Expected investment return", 0.0, 0.12,
        float(st.session_state.ledger.investment_return), 0.005,
    )
    st.session_state.ledger.salary_growth = st.slider(
        "Salary growth", 0.0, 0.08,
        float(st.session_state.ledger.salary_growth), 0.005,
    )

if st.sidebar.button("Load demo data", type="primary"):
    st.session_state.ledger = seed_ledger(CohortLedger(
        piu_price=1.0,
        valuation_year=st.session_state.ledger.valuation_year,
        discount_rate=st.session_state.ledger.discount_rate,
        salary_growth=st.session_state.ledger.salary_growth,
        investment_return=st.session_state.ledger.investment_return,
    ))
    st.session_state.event_log.append("demo_data_loaded",
                                       members=len(st.session_state.ledger))
    st.rerun()

if st.sidebar.button("Reset ledger"):
    st.session_state.ledger = CohortLedger(piu_price=1.0)
    st.session_state.event_log = EventLog()
    st.rerun()

st.sidebar.caption(
    f"{len(st.session_state.ledger)} members · "
    f"{len(st.session_state.event_log)} audit events"
)


ledger: CohortLedger = st.session_state.ledger
event_log: EventLog = st.session_state.event_log


# --------------------------------------------------------------------------- header
st.title("Aequitas — Intergenerationally-Fair Pension Prototype")
st.caption(
    "A Master's capstone prototype combining actuarial valuation, stochastic "
    "projection, and governance fairness checks."
)

(
    tab_over,
    tab_members,
    tab_val,
    tab_proj,
    tab_mc,
    tab_fair,
    tab_gov,
    tab_stress,
    tab_audit,
    tab_contracts,
) = st.tabs(
    [
        "Overview",
        "Members",
        "Actuarial Valuation",
        "Projections",
        "Monte Carlo",
        "Fairness",
        "Governance Sandbox",
        "Fairness Stress",
        "Audit Chain",
        "Contracts",
    ]
)


# =========================================================================== 1
with tab_over:
    st.subheader("Scheme overview")

    if len(ledger) == 0:
        st.info("No members yet. Click **Load demo data** in the sidebar.")
    else:
        valuations = ledger.value_all()
        epv_b = sum(v.epv_benefits for v in valuations)
        epv_c = sum(v.epv_contributions for v in valuations)
        mwr = epv_b / epv_c if epv_c else 0.0
        funded_ratio = (sum(m.total_contributions for m in ledger) + 1e-9) / (epv_b + 1e-9)

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Members", len(ledger))
        c2.metric("EPV contributions", f"{epv_c:,.0f}")
        c3.metric("EPV benefits", f"{epv_b:,.0f}")
        c4.metric("Scheme MWR", f"{mwr:.2f}")

        st.markdown("##### Aggregate fund projection (deterministic)")
        fund_df = project_fund(
            ledger.get_all_members(),
            valuation_year=ledger.valuation_year,
            salary_growth=ledger.salary_growth,
            investment_return=ledger.investment_return,
            discount_rate=ledger.discount_rate,
            horizon=60,
        )
        if not fund_df.empty:
            st.line_chart(
                fund_df.set_index("year")[["fund_value", "contributions", "benefit_payments"]],
                height=320,
            )
            with st.expander("Show projection data"):
                st.dataframe(fund_df, use_container_width=True, hide_index=True)


# =========================================================================== 2
with tab_members:
    st.subheader("Member registry")

    with st.form("register_form"):
        c1, c2, c3 = st.columns(3)
        with c1:
            wallet = st.text_input("Wallet / Member ID")
            birth_year = st.number_input("Birth year",
                                         min_value=1940, max_value=2010,
                                         value=1975, step=1)
        with c2:
            salary = st.number_input("Salary", min_value=0.0, value=50000.0, step=1000.0)
            contribution_rate = st.slider("Contribution rate", 0.0, 0.25, 0.10, 0.01)
        with c3:
            retirement_age = st.number_input("Retirement age",
                                             min_value=55, max_value=75,
                                             value=65, step=1)
            sex = st.selectbox("Sex (for mortality loading)",
                               ["U", "M", "F"], index=0)
        register_submit = st.form_submit_button("Register")
        if register_submit:
            try:
                if not wallet.strip():
                    raise ValueError("Wallet / Member ID cannot be empty")
                ledger.register_member(
                    wallet=wallet.strip(),
                    birth_year=int(birth_year),
                    salary=float(salary),
                    contribution_rate=float(contribution_rate),
                    retirement_age=int(retirement_age),
                    sex=sex,
                )
                event_log.append("member_registered",
                                 wallet=wallet.strip(),
                                 birth_year=int(birth_year))
                st.success(f"Registered {wallet}")
            except Exception as exc:
                st.error(str(exc))

    with st.form("contribution_form"):
        c1, c2 = st.columns([2, 1])
        contrib_wallet = c1.text_input("Wallet / Member ID for contribution")
        amount = c2.number_input("Amount", min_value=0.0, value=1000.0, step=100.0)
        contrib_submit = st.form_submit_button("Contribute")
        if contrib_submit:
            try:
                if not contrib_wallet.strip():
                    raise ValueError("Wallet / Member ID cannot be empty")
                piu = ledger.contribute(contrib_wallet.strip(), float(amount))
                event_log.append("contribution_recorded",
                                 wallet=contrib_wallet.strip(),
                                 amount=float(amount),
                                 piu_minted=float(piu))
                st.success(f"PIUs minted: {piu:.2f}")
            except Exception as exc:
                st.error(str(exc))

    st.markdown("##### Current roster")
    members = ledger.get_all_members()
    if members:
        df = pd.DataFrame([m.to_dict() for m in members])
        df["age"] = ledger.valuation_year - df["birth_year"]
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.info("No members yet.")

    st.markdown("##### Cohort contribution totals")
    if ledger.cohort_aggregate_contrib:
        cohort_df = (
            pd.DataFrame(
                [{"cohort": k, "total_contributions": v}
                 for k, v in ledger.cohort_aggregate_contrib.items()]
            )
            .sort_values("cohort")
            .reset_index(drop=True)
        )
        st.bar_chart(cohort_df.set_index("cohort"), height=260)
        st.dataframe(cohort_df, use_container_width=True, hide_index=True)


# =========================================================================== 3
with tab_val:
    st.subheader("Actuarial valuation")

    st.markdown(
        "EPVs are computed member-by-member using a Gompertz–Makeham life "
        "table and a classical annuity-due factor. Money's Worth Ratio = "
        "EPV(benefits) / EPV(contributions). Parity is MWR = 1.00."
    )

    if len(ledger) == 0:
        st.info("Load demo data to populate valuations.")
    else:
        valuations = ledger.value_all()
        df = pd.DataFrame([v.__dict__ for v in valuations])
        df = df.merge(
            pd.DataFrame([{"wallet": m.wallet, "cohort": m.cohort}
                          for m in ledger]),
            on="wallet",
        )
        st.markdown("##### Per-member valuation")
        st.dataframe(
            df.style.format({
                "epv_contributions": "{:,.0f}",
                "epv_benefits": "{:,.0f}",
                "money_worth_ratio": "{:.2f}",
                "projected_annual_benefit": "{:,.0f}",
                "replacement_ratio": "{:.2%}",
            }),
            use_container_width=True,
        )

        st.markdown("##### Cohort valuation")
        cv = ledger.cohort_valuation()
        cv_df = (
            pd.DataFrame([
                {"cohort": c, **row} for c, row in cv.items()
            ])
            .sort_values("cohort")
            .reset_index(drop=True)
        )
        st.dataframe(
            cv_df.style.format({
                "epv_contributions": "{:,.0f}",
                "epv_benefits": "{:,.0f}",
                "money_worth_ratio": "{:.2f}",
            }),
            use_container_width=True, hide_index=True,
        )
        st.markdown("MWR by cohort (parity = 1.00)")
        st.bar_chart(cv_df.set_index("cohort")["money_worth_ratio"], height=260)

    with st.expander("Mortality table (life expectancy by age)"):
        table = act.default_table("U")
        ages = list(range(20, 95, 5))
        life_df = pd.DataFrame({
            "age": ages,
            "l_x": [round(table.l_x(a), 1) for a in ages],
            "life_expectancy": [round(table.life_expectancy(a), 2) for a in ages],
            "annuity_due_ax": [
                round(act.annuity_due(table, a, ledger.discount_rate), 3)
                for a in ages
            ],
        })
        st.dataframe(life_df, use_container_width=True, hide_index=True)


# =========================================================================== 4
with tab_proj:
    st.subheader("Deterministic projections")

    if len(ledger) == 0:
        st.info("Load demo data to project members.")
    else:
        wallets = [m.wallet for m in ledger]
        w = st.selectbox("Select member", wallets)
        member = ledger.get_member_summary(w)
        df = project_member(
            member,
            valuation_year=ledger.valuation_year,
            salary_growth=ledger.salary_growth,
            investment_return=ledger.investment_return,
            discount_rate=ledger.discount_rate,
            horizon=60,
        )

        c1, c2, c3 = st.columns(3)
        c1.metric("Current age", member.age(ledger.valuation_year))
        retired_df = df[df.phase == "retired"]
        first_benefit = retired_df["benefit_payment"].iloc[0] if not retired_df.empty else 0.0
        c2.metric("Annual benefit at retirement", f"{first_benefit:,.0f}")
        accum_df = df[df.phase == "accumulation"]
        peak = accum_df["fund_value"].max() if not accum_df.empty else 0.0
        c3.metric("Fund value at retirement", f"{peak:,.0f}")

        st.markdown("##### Fund, contributions and benefits over time")
        st.line_chart(
            df.set_index("year")[["fund_value", "contribution", "benefit_payment"]],
            height=320,
        )
        st.markdown("##### Projection detail")
        st.dataframe(df, use_container_width=True, hide_index=True)


# =========================================================================== 5
with tab_mc:
    st.subheader("Monte Carlo — stochastic outcomes")

    if len(ledger) == 0:
        st.info("Load demo data to run simulations.")
    else:
        c1, c2, c3 = st.columns(3)
        n_paths = c1.number_input("Paths", min_value=200, max_value=20_000,
                                  value=2_000, step=200)
        sigma = c2.slider("Return volatility σ", 0.01, 0.30, 0.10, 0.01)
        seed = c3.number_input("Seed", value=42, step=1)

        wallets = [m.wallet for m in ledger]
        w = st.selectbox("Member", wallets, key="mc_member")
        member = ledger.get_member_summary(w)

        result = simulate_member(
            member,
            valuation_year=ledger.valuation_year,
            n_paths=int(n_paths),
            mu=ledger.investment_return,
            sigma=float(sigma),
            salary_growth=ledger.salary_growth,
            discount_rate=ledger.discount_rate,
            seed=int(seed),
        )
        st.markdown("##### Percentiles of retirement outcomes")
        st.dataframe(
            result["percentiles"].style.format({
                "fund_at_retirement": "{:,.0f}",
                "annual_benefit": "{:,.0f}",
                "replacement_ratio": "{:.2%}",
            }),
            use_container_width=True,
        )

        st.markdown("##### Fan chart of fund value")
        st.line_chart(result["time_series"].set_index("year"), height=320)

        st.markdown("##### Distribution of annual benefit at retirement")
        hist = (
            pd.cut(result["paths"]["annual_benefit"], bins=40)
            .value_counts()
            .sort_index()
        )
        hist_df = pd.DataFrame({
            "benefit": [iv.mid for iv in hist.index],
            "count": hist.values,
        })
        st.bar_chart(hist_df.set_index("benefit"), height=300)

        st.markdown("##### Scheme-level aggregate fan")
        agg = simulate_fund(
            ledger.get_all_members(),
            valuation_year=ledger.valuation_year,
            n_paths=min(int(n_paths), 1_000),
            mu=ledger.investment_return,
            sigma=float(sigma),
            salary_growth=ledger.salary_growth,
            discount_rate=ledger.discount_rate,
            seed=int(seed),
        )
        if not agg.empty:
            st.line_chart(agg.set_index("year"), height=320)


# =========================================================================== 6
with tab_fair:
    st.subheader("Fairness diagnostics")

    st.markdown(
        "A fair scheme is one in which every cohort's Money's Worth Ratio "
        "stays close to 1.0 and close to every other cohort's. Three "
        "complementary views:"
    )

    if len(ledger) < 2:
        st.info("Register at least 2 members across 2+ cohorts.")
    else:
        cv = ledger.cohort_valuation()
        mwrs = {c: cv[c]["money_worth_ratio"] for c in cv}
        disp = mwr_dispersion(mwrs)
        gini = mwr_gini(mwrs)
        idx = intergenerational_index(mwrs)

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("MWR min → max", f"{disp['min']:.2f} → {disp['max']:.2f}")
        c2.metric("MWR std dev", f"{disp['std']:.3f}")
        c3.metric("Gini (MWR)", f"{gini:.3f}")
        c4.metric("Intergenerational index", f"{idx:.3f}")

        mwr_df = (
            pd.DataFrame([{"cohort": k, "mwr": v} for k, v in mwrs.items()])
            .sort_values("cohort")
            .reset_index(drop=True)
        )
        st.bar_chart(mwr_df.set_index("cohort"), height=280)

        st.markdown("##### Original MVP corridor check (demo)")
        if len(ledger.cohort_aggregate_contrib) >= 3:
            sorted_cohorts = sorted(ledger.cohort_aggregate_contrib.keys())[:3]
            cohort_epvs_old = {
                c: ledger.cohort_aggregate_contrib[c] * 100 for c in sorted_cohorts
            }
            scenario = st.selectbox("Proposal", ["Balanced change", "Unfair change"])
            if scenario == "Balanced change":
                cohort_epvs_new = {c: e * 1.02 for c, e in cohort_epvs_old.items()}
            else:
                cohort_epvs_new = {
                    sorted_cohorts[0]: cohort_epvs_old[sorted_cohorts[0]] * 1.10,
                    sorted_cohorts[1]: cohort_epvs_old[sorted_cohorts[1]] * 1.00,
                    sorted_cohorts[2]: cohort_epvs_old[sorted_cohorts[2]] * 0.82,
                }
            epv_bench = sum(cohort_epvs_old.values()) / len(cohort_epvs_old)
            result = fairness_corridor_check(cohort_epvs_old, cohort_epvs_new,
                                             epv_bench, delta=0.05)
            c1, c2 = st.columns(2)
            with c1:
                st.write("Old EPVs", cohort_epvs_old)
                st.write("New EPVs", {k: round(v, 2) for k, v in cohort_epvs_new.items()})
            with c2:
                st.metric("Max pairwise deviation", f"{result['max_deviation']:.2%}")
                st.metric("Allowed", f"{result['delta_limit']:.0%}")
                if result["passes"]:
                    st.success("PASSES")
                else:
                    st.error(f"FAILS — worst pair {result['worst_pair']}")
        else:
            st.info("≥3 cohorts needed for corridor demo.")


# =========================================================================== 7
with tab_gov:
    st.subheader("Governance sandbox")

    st.markdown(
        "Propose a benefit change per cohort as a multiplier (1.00 = no "
        "change). Aequitas evaluates the proposal against the fairness "
        "corridor and every decision is written to the audit chain."
    )
    if len(ledger) < 2:
        st.info("Load demo data to use the sandbox.")
    else:
        cohorts = sorted(ledger.cohort_valuation().keys())
        st.markdown("##### Set cohort multipliers")
        cols = st.columns(min(len(cohorts), 6) or 1)
        multipliers: dict[int, float] = {}
        for i, cohort in enumerate(cohorts):
            col = cols[i % len(cols)]
            multipliers[cohort] = col.slider(
                f"Cohort {cohort}", 0.70, 1.30, 1.00, 0.01, key=f"mult_{cohort}",
            )

        delta = st.slider("Fairness corridor δ", 0.01, 0.25, 0.05, 0.01)
        name = st.text_input("Proposal name", "Cohort adjustment")

        if st.button("Evaluate proposal"):
            cv = ledger.cohort_valuation()
            outcome = evaluate_proposal(cv, multipliers, delta=delta)
            event_log.append("proposal_evaluated",
                             name=name,
                             multipliers={int(k): float(v) for k, v in multipliers.items()},
                             passes=bool(outcome["passes"]),
                             gini_before=round(outcome["gini_before"], 4),
                             gini_after=round(outcome["gini_after"], 4),
                             index_before=round(outcome["index_before"], 4),
                             index_after=round(outcome["index_after"], 4))
            c1, c2, c3 = st.columns(3)
            c1.metric("Gini MWR", f"{outcome['gini_after']:.3f}",
                      delta=f"{outcome['gini_after'] - outcome['gini_before']:+.3f}")
            c2.metric("Intergen index", f"{outcome['index_after']:.3f}",
                      delta=f"{outcome['index_after'] - outcome['index_before']:+.3f}")
            c3.metric("Corridor passes?", "YES" if outcome["passes"] else "NO")

            compare_df = pd.DataFrame({
                "cohort": list(outcome["mwr_before"].keys()),
                "mwr_before": list(outcome["mwr_before"].values()),
                "mwr_after": list(outcome["mwr_after"].values()),
            }).sort_values("cohort")
            st.bar_chart(compare_df.set_index("cohort"), height=300)
            st.dataframe(compare_df, use_container_width=True, hide_index=True)


# =========================================================================== 8
with tab_stress:
    st.subheader("Fairness stress — stochastic cohort shocks")
    st.markdown(
        "This layer models the *economic environment a cohort lived through* "
        "— things the actuarial model cannot capture (inflation regimes, "
        "housing affordability, labour precarity, policy erosion). For each "
        "Monte-Carlo scenario s, every cohort c is hit by\n\n"
        "`m_c(s) = 1 + β_c · F(s) + ε_c(s)`\n\n"
        "where `F(s) ~ N(0, σ_F²)` is a shared macro shock, `ε_c(s) ~ "
        "N(0, σ_ε²)` is idiosyncratic noise, and β_c varies linearly by "
        "birth year (older → positive, younger → negative by default)."
    )

    if len(ledger) < 2:
        st.info("Load demo data to run the stress test.")
    else:
        c1, c2, c3 = st.columns(3)
        n_scen = c1.number_input("Scenarios (S)",
                                 min_value=200, max_value=20_000,
                                 value=2_000, step=200)
        factor_sigma = c2.slider("Macro factor σ_F", 0.0, 0.30, 0.10, 0.01)
        idio_sigma = c3.slider("Idiosyncratic σ_ε", 0.0, 0.15, 0.03, 0.005)

        c4, c5, c6 = st.columns(3)
        gen_slope = c4.slider("Generational slope |β_max|",
                              0.0, 1.0, 0.50, 0.05,
                              help="Controls how strongly older and "
                                   "younger cohorts load on F. 0 → no macro "
                                   "exposure, only idiosyncratic noise.")
        corridor_delta = c5.slider("Corridor δ", 0.01, 0.20, 0.05, 0.01)
        poor_thr = c6.slider("Youngest-poor threshold (MWR)",
                             0.50, 1.00, 0.90, 0.05)
        seed = st.number_input("Seed", value=42, step=1, key="stress_seed")

        cv = ledger.cohort_valuation()
        result = stochastic_cohort_stress(
            cv,
            n_scenarios=int(n_scen),
            factor_sigma=float(factor_sigma),
            idiosyncratic_sigma=float(idio_sigma),
            generational_slope=float(gen_slope),
            corridor_delta=float(corridor_delta),
            youngest_poor_threshold=float(poor_thr),
            seed=int(seed),
        )

        # KPIs
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Mean Gini", f"{result['mean_gini']:.3f}")
        k2.metric("p95 Gini (worst-case)", f"{result['p95_gini']:.3f}")
        k3.metric("Mean intergen index", f"{result['mean_index']:.3f}")
        k4.metric("p05 intergen index", f"{result['p05_index']:.3f}")

        k5, k6 = st.columns(2)
        k5.metric("Corridor pass rate", f"{result['corridor_pass_rate']:.1%}")
        k6.metric(
            f"P(MWR{result['youngest_cohort']} < "
            f"{result['youngest_poor_threshold']:.2f})",
            f"{result['youngest_poor_rate']:.1%}",
            help="How often the youngest cohort ends up with a poor MWR.",
        )

        st.markdown("##### Cohort betas used")
        beta_df = (
            pd.DataFrame(
                [{"cohort": c, "beta": b} for c, b in result["betas"].items()]
            )
            .sort_values("cohort")
            .reset_index(drop=True)
        )
        st.bar_chart(beta_df.set_index("cohort"), height=240)

        st.markdown("##### How often each cohort is the worst-affected")
        worst_df = (
            pd.DataFrame(
                [{"cohort": c, "freq": f}
                 for c, f in result["worst_cohort_freq"].items()]
            )
            .sort_values("cohort")
            .reset_index(drop=True)
        )
        st.bar_chart(worst_df.set_index("cohort"), height=280)
        st.dataframe(worst_df.style.format({"freq": "{:.1%}"}),
                     use_container_width=True, hide_index=True)

        st.markdown("##### Distribution of Gini and intergen index")
        dist_df = pd.DataFrame({
            "gini": result["gini_series"],
            "intergen_index": result["index_series"],
        })
        st.bar_chart(
            pd.cut(dist_df["gini"], bins=30).value_counts()
              .sort_index().rename_axis("bin").reset_index(drop=True),
            height=220,
        )
        with st.expander("Show per-scenario MWRs (sample)"):
            st.dataframe(
                result["mwr_samples_df"].head(100)
                    .style.format("{:.3f}"),
                use_container_width=True,
            )

        st.markdown("##### Summary")
        st.dataframe(summary_frame(result),
                     use_container_width=True, hide_index=True)

        if st.button("Record stress test to audit chain"):
            event_log.append(
                "fairness_stress_run",
                n_scenarios=result["n_scenarios"],
                factor_sigma=result["factor_sigma"],
                idiosyncratic_sigma=result["idiosyncratic_sigma"],
                mean_gini=round(result["mean_gini"], 4),
                p95_gini=round(result["p95_gini"], 4),
                corridor_pass_rate=round(result["corridor_pass_rate"], 4),
                youngest_poor_rate=round(result["youngest_poor_rate"], 4),
            )
            st.success("Recorded to audit chain.")


# =========================================================================== 9
with tab_audit:
    st.subheader("Audit chain (smart-contract mirror)")
    st.caption(
        "Every governance-relevant action is hashed into an append-only "
        "chain. Verification re-computes every hash from the genesis block."
    )
    if len(event_log) == 0:
        st.info("No events recorded yet.")
    else:
        verified = event_log.verify()
        (st.success if verified else st.error)(
            f"Chain integrity: {'VERIFIED' if verified else 'TAMPERED'} — "
            f"{len(event_log)} events"
        )
        df = pd.DataFrame([
            {
                "seq": e.seq,
                "event_type": e.event_type,
                "data": e.data,
                "hash": e.hash[:10] + "…",
                "prev_hash": e.prev_hash[:10] + "…",
            }
            for e in event_log
        ])
        st.dataframe(df, use_container_width=True, hide_index=True)


# =========================================================================== 10
with tab_contracts:
    st.subheader("Contracts — Python ↔ chain bridge")
    st.caption(
        "The Python engine is the actuarial brain. Every governance-relevant "
        "action (register, contribute, baseline, proposal, stress) is "
        "translated into the exact on-chain call that the Solidity contracts "
        "in `contracts/src/` expect. This tab previews those payloads — "
        "nothing is submitted to a network, it just shows what would be sent."
    )

    st.markdown(
        """
        **Hybrid architecture**

        * **Off-chain (Python)** — `engine.ledger`, `engine.actuarial`,
          `engine.simulation`, `engine.fairness_stress`.
        * **On-chain (Solidity)** — `CohortLedger`, `FairnessGate`,
          `MortalityOracle`, `LongevaPool`, `BenefitStreamer`, `VestaRouter`,
          `StressOracle`, `BackstopVault`.
        * **Bridge** — `engine.chain_bridge` (1e18 fixed-point, uint16 cohorts,
          bytes32 reason codes, sha-256 data hashes).
        """
    )

    if len(ledger) == 0:
        st.info("Load demo data in the sidebar to see bridged calls.")
    else:
        st.markdown("##### Ledger → CohortLedger.sol")
        calls = ledger_to_chain_calls(ledger)
        st.caption(f"{len(calls)} calls that replay the current ledger on chain.")
        st.json(calls_to_json(calls[:10]))
        if len(calls) > 10:
            st.caption(f"(showing first 10 of {len(calls)})")

        st.markdown("##### Cohort valuation → FairnessGate.setBaseline")
        cv = ledger.cohort_valuation()
        st.json(encode_baseline(cv).as_dict())

        st.markdown("##### Stage a proposal → FairnessGate.submitAndEvaluate")
        cohorts = sorted(cv.keys())
        prop_col1, prop_col2 = st.columns([2, 1])
        with prop_col1:
            prop_name = st.text_input(
                "Proposal name",
                value="Trim youngest cohort by 3%",
                key="bridge_prop_name",
            )
        with prop_col2:
            delta_pct = st.number_input(
                "Corridor δ (%)", value=5.0, min_value=0.1, max_value=50.0, step=0.5,
                key="bridge_delta",
            )
        mult_inputs: dict[int, float] = {}
        mcols = st.columns(min(4, max(1, len(cohorts))))
        for i, c in enumerate(cohorts):
            with mcols[i % len(mcols)]:
                mult_inputs[c] = st.number_input(
                    f"{c} multiplier", value=0.97 if c == cohorts[-1] else 1.0,
                    min_value=0.5, max_value=1.5, step=0.01,
                    key=f"bridge_mult_{c}",
                )
        proposal = Proposal(
            name=prop_name,
            description="Bridge preview",
            multipliers=mult_inputs,
        )
        st.json(encode_proposal(proposal, cv, delta=delta_pct / 100.0).as_dict())

        st.markdown("##### Stress summary → StressOracle.updateStressLevel")
        stress_level = st.slider(
            "Stress level (0 = calm, 1 = severe)", 0.0, 1.0, 0.25, 0.05,
            key="bridge_stress_level",
        )
        reason = st.text_input(
            "Reason code (≤31 chars)", value="p95_gini>threshold",
            key="bridge_reason",
        )
        summary = {
            "n_members": len(ledger),
            "n_cohorts": len(cv),
            "stress_level": stress_level,
        }
        st.json(encode_stress_update(stress_level, reason, str(summary)).as_dict())

        if st.button("Record bridge hand-off to audit chain"):
            event_log.append(
                "bridge_handoff",
                calls=len(calls),
                cohorts=len(cv),
                proposal=prop_name,
                stress_level=stress_level,
            )
            st.success("Hand-off hashed into audit chain.")
