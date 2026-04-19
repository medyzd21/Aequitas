"""Aequitas — pension intelligence terminal.

Dashboard-style Streamlit front-end over the off-chain actuarial engine and
the on-chain execution layer. Five sections, Arkham-style layout:

    1. Fund Overview         — KPI strip + fund projection + cohort signals
    2. Members & Cohorts     — roster, valuation, projections, Monte Carlo
    3. Fairness & Governance — corridor, sandbox, stochastic stress
    4. Operations Feed       — append-only audit chain of governance events
    5. On-Chain / Contracts  — deployed addresses + bridge payload previews

Run locally:

    streamlit run app.py

The dark theme lives in `.streamlit/config.toml`.
"""
from __future__ import annotations

from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

from engine import actuarial as act
from engine.chain_bridge import (
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
from engine.chain_stub import EventLog
from engine.deployments import load_latest
from engine.fairness import (
    evaluate_proposal,
    fairness_corridor_check,
    intergenerational_index,
    mwr_dispersion,
    mwr_gini,
)
from engine.fairness_stress import stochastic_cohort_stress, summary_frame
from engine.ledger import CohortLedger
from engine.models import Proposal
from engine.projection import project_fund, project_member
from engine.seed import seed_ledger
from engine.simulation import simulate_fund, simulate_member


# --------------------------------------------------------------------------- page
st.set_page_config(
    page_title="Aequitas — Pension Intelligence",
    layout="wide",
    page_icon=":bar_chart:",
)

# palette (must match .streamlit/config.toml)
PALETTE = {
    "bg":        "#0b1220",
    "panel":     "#111a2e",
    "edge":      "#1f2a44",
    "text":      "#e2e8f0",
    "muted":     "#94a3b8",
    "accent":    "#38bdf8",   # cyan
    "good":      "#34d399",   # emerald
    "warn":      "#f59e0b",   # amber
    "bad":       "#ef4444",   # red
    "series":    ["#38bdf8", "#a78bfa", "#34d399", "#f59e0b", "#f472b6", "#60a5fa"],
}


def _alt_theme() -> dict:
    return {
        "config": {
            "background": PALETTE["bg"],
            "view": {"stroke": "transparent"},
            "title": {"color": PALETTE["text"], "fontSize": 14, "anchor": "start"},
            "axis": {
                "labelColor": PALETTE["muted"],
                "titleColor": PALETTE["muted"],
                "gridColor": PALETTE["edge"],
                "domainColor": PALETTE["edge"],
                "tickColor": PALETTE["edge"],
            },
            "legend": {
                "labelColor": PALETTE["text"],
                "titleColor": PALETTE["muted"],
            },
            "range": {"category": PALETTE["series"]},
        }
    }


alt.themes.register("aequitas", _alt_theme)
alt.themes.enable("aequitas")


# --------------------------------------------------------------------------- CSS
st.markdown(
    f"""
    <style>
      /* Sticky KPI strip */
      .kpi-strip {{
        position: sticky; top: 0; z-index: 50;
        background: {PALETTE['panel']};
        border: 1px solid {PALETTE['edge']};
        border-radius: 10px;
        padding: 10px 14px;
        margin-bottom: 10px;
        box-shadow: 0 2px 10px rgba(0,0,0,0.25);
      }}
      .kpi-label {{
        color: {PALETTE['muted']};
        font-size: 11px; letter-spacing: 0.06em; text-transform: uppercase;
      }}
      .kpi-value {{
        color: {PALETTE['text']};
        font-size: 20px; font-weight: 600; line-height: 1.2;
      }}
      .kpi-sub {{
        color: {PALETTE['muted']}; font-size: 11px;
      }}
      .pill {{
        display: inline-block; padding: 2px 8px;
        border-radius: 999px; font-size: 11px; font-weight: 600;
        letter-spacing: 0.04em;
      }}
      .pill-good {{ background: rgba(52,211,153,0.15); color: {PALETTE['good']}; border: 1px solid {PALETTE['good']}; }}
      .pill-warn {{ background: rgba(245,158,11,0.15); color: {PALETTE['warn']}; border: 1px solid {PALETTE['warn']}; }}
      .pill-bad  {{ background: rgba(239,68,68,0.15);  color: {PALETTE['bad']};  border: 1px solid {PALETTE['bad']}; }}
      .pill-muted{{ background: rgba(148,163,184,0.12); color: {PALETTE['muted']}; border: 1px solid {PALETTE['edge']}; }}
      .ribbon {{
        background: {PALETTE['panel']};
        border: 1px solid {PALETTE['edge']};
        border-radius: 8px;
        padding: 8px 12px;
        margin-bottom: 10px;
        font-size: 12px;
        color: {PALETTE['muted']};
      }}
      .section-title {{
        color: {PALETTE['text']}; font-size: 18px; font-weight: 600;
        margin-top: 4px; margin-bottom: 4px;
      }}
      .section-sub {{
        color: {PALETTE['muted']}; font-size: 12px;
        margin-bottom: 10px;
      }}
      /* Tighter tabs so the dashboard feels dense */
      button[data-baseweb="tab"] {{ padding: 6px 14px !important; }}
    </style>
    """,
    unsafe_allow_html=True,
)


# --------------------------------------------------------------------------- state
def _init_state() -> None:
    if "ledger" not in st.session_state:
        st.session_state.ledger = CohortLedger(piu_price=1.0)
    if "event_log" not in st.session_state:
        st.session_state.event_log = EventLog()
    if "cached_stress" not in st.session_state:
        st.session_state.cached_stress = None


_init_state()


# --------------------------------------------------------------------------- sidebar
with st.sidebar:
    st.markdown("### Aequitas")
    st.caption("Pension intelligence terminal — capstone prototype")

    with st.expander("Assumptions", expanded=True):
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

    if st.button("Load demo data", type="primary", use_container_width=True):
        st.session_state.ledger = seed_ledger(CohortLedger(
            piu_price=1.0,
            valuation_year=st.session_state.ledger.valuation_year,
            discount_rate=st.session_state.ledger.discount_rate,
            salary_growth=st.session_state.ledger.salary_growth,
            investment_return=st.session_state.ledger.investment_return,
        ))
        st.session_state.event_log.append(
            "demo_data_loaded", members=len(st.session_state.ledger)
        )
        st.rerun()

    if st.button("Reset ledger", use_container_width=True):
        st.session_state.ledger = CohortLedger(piu_price=1.0)
        st.session_state.event_log = EventLog()
        st.session_state.cached_stress = None
        st.rerun()

    st.caption(
        f"{len(st.session_state.ledger)} members · "
        f"{len(st.session_state.event_log)} audit events"
    )

    with st.expander("About the split"):
        st.caption(
            "**Off-chain (Python):** Gompertz–Makeham mortality, EPVs, MWRs, "
            "Gini, Monte-Carlo cohort stress.\n\n"
            "**On-chain (Solidity):** CohortLedger, FairnessGate, "
            "MortalityOracle, LongevaPool, BenefitStreamer, VestaRouter, "
            "StressOracle, BackstopVault.\n\n"
            "**Bridge:** `engine.chain_bridge` (1e18 fixed-point, uint16 "
            "cohorts, bytes32 reasons)."
        )


ledger: CohortLedger = st.session_state.ledger
event_log: EventLog = st.session_state.event_log


# --------------------------------------------------------------------------- header
st.markdown(
    "<div style='margin-bottom:2px;'>"
    "<span style='color:#94a3b8; font-size:12px; letter-spacing:0.15em;'>"
    "AEQUITAS · INTERGENERATIONALLY-FAIR PENSION"
    "</span></div>",
    unsafe_allow_html=True,
)
st.markdown(
    "<div style='color:#e2e8f0; font-size:26px; font-weight:700; margin-bottom:8px;'>"
    "Pension Intelligence Terminal"
    "</div>",
    unsafe_allow_html=True,
)


# --------------------------------------------------------------------------- KPI helpers
def _fund_kpis() -> dict:
    if len(ledger) == 0:
        return {
            "members": 0, "cohorts": 0,
            "epv_c": 0.0, "epv_b": 0.0,
            "mwr": 0.0, "funded_ratio": 0.0,
            "gini": 0.0, "intergen": 0.0,
            "corridor_pass": None, "stress_level": None,
        }
    valuations = ledger.value_all()
    epv_b = sum(v.epv_benefits for v in valuations)
    epv_c = sum(v.epv_contributions for v in valuations)
    mwr = epv_b / epv_c if epv_c else 0.0
    contribs_to_date = sum(m.total_contributions for m in ledger)
    funded_ratio = (contribs_to_date + 1e-9) / (epv_b + 1e-9)

    cv = ledger.cohort_valuation()
    mwrs = {c: cv[c]["money_worth_ratio"] for c in cv}
    gini = mwr_gini(mwrs) if len(mwrs) >= 2 else 0.0
    intergen = intergenerational_index(mwrs) if len(mwrs) >= 2 else 1.0

    # Derive corridor pass + stress from cached stress run if available
    cached = st.session_state.cached_stress
    corridor_pass = cached["corridor_pass_rate"] if cached else None
    stress_level = cached["p95_gini"] if cached else None

    return {
        "members": len(ledger), "cohorts": len(cv),
        "epv_c": epv_c, "epv_b": epv_b,
        "mwr": mwr, "funded_ratio": funded_ratio,
        "gini": gini, "intergen": intergen,
        "corridor_pass": corridor_pass, "stress_level": stress_level,
    }


def _kpi_cell(label: str, value: str, sub: str = "") -> str:
    sub_html = f"<div class='kpi-sub'>{sub}</div>" if sub else ""
    return (
        f"<div>"
        f"<div class='kpi-label'>{label}</div>"
        f"<div class='kpi-value'>{value}</div>"
        f"{sub_html}"
        f"</div>"
    )


def _status_pill(value: float | None, good: float, warn: float, *, higher_is_better: bool = True, suffix: str = "") -> str:
    if value is None:
        return "<span class='pill pill-muted'>NO DATA</span>"
    if higher_is_better:
        if value >= good:
            klass, label = "pill-good", "HEALTHY"
        elif value >= warn:
            klass, label = "pill-warn", "WATCH"
        else:
            klass, label = "pill-bad", "STRESS"
    else:
        if value <= good:
            klass, label = "pill-good", "HEALTHY"
        elif value <= warn:
            klass, label = "pill-warn", "WATCH"
        else:
            klass, label = "pill-bad", "STRESS"
    return f"<span class='pill {klass}'>{label}{suffix}</span>"


def _pretty_event(e) -> str:
    """Render an audit-log event as a human-readable sentence."""
    t = e.event_type
    d = e.data or {}
    if t == "demo_data_loaded":
        return f"Demo dataset loaded — {d.get('members', '?')} members seeded into the ledger."
    if t == "member_registered":
        return (f"Member {d.get('wallet', '?')} registered "
                f"(birth year {d.get('birth_year', '?')}).")
    if t == "contribution_recorded":
        amt = d.get('amount', 0) or 0
        piu = d.get('piu_minted', 0) or 0
        return (f"Contribution from {d.get('wallet', '?')} — "
                f"{amt:,.0f} recorded, {piu:.2f} PIUs minted.")
    if t == "proposal_evaluated":
        name = d.get('name', 'Proposal')
        verdict = "PASSED corridor" if d.get('passes') else "FAILED corridor"
        g0, g1 = d.get('gini_before', 0) or 0, d.get('gini_after', 0) or 0
        return (f"Proposal '{name}' {verdict} — "
                f"Gini {g0:.3f} → {g1:.3f} ({g1 - g0:+.3f}).")
    if t == "fairness_stress_run":
        return (f"Fairness stress run — {d.get('n_scenarios', '?')} scenarios, "
                f"p95 Gini {d.get('p95_gini', 0) or 0:.3f}, "
                f"corridor pass {d.get('corridor_pass_rate', 0) or 0:.0%}, "
                f"youngest-poor {d.get('youngest_poor_rate', 0) or 0:.0%}.")
    if t == "bridge_handoff":
        return (f"Bridge hand-off — {d.get('calls', '?')} on-chain calls across "
                f"{d.get('cohorts', '?')} cohorts, stress level "
                f"{d.get('stress_level', 0) or 0:.2f}.")
    return f"{t} — {d}"


def _action_card(name: str, actor: str, target: str, economic: str, actuarial: str) -> None:
    """Render a human-readable header for a bridged on-chain action."""
    st.markdown(
        f"<div style='background: {PALETTE['panel']}; "
        f"border: 1px solid {PALETTE['edge']}; "
        f"border-left: 3px solid {PALETTE['accent']}; "
        f"border-radius: 8px; padding: 12px 14px; margin-bottom: 8px;'>"
        f"<div style='display:flex; justify-content:space-between; "
        f"align-items:center; margin-bottom:8px; flex-wrap:wrap; gap:6px;'>"
        f"<div style='color:{PALETTE['text']}; font-size:14px; font-weight:600;'>"
        f"{name}</div>"
        f"<div style='font-size:11px;'>"
        f"<span class='pill pill-muted'>{actor}</span> "
        f"<span style='color:{PALETTE['muted']}'>&rarr;</span> "
        f"<span class='pill pill-good'>{target}</span>"
        f"</div></div>"
        f"<div style='color:{PALETTE['text']}; font-size:12px; line-height:1.5; "
        f"margin-bottom:4px;'>"
        f"<span style='color:{PALETTE['accent']}; font-weight:600;'>Economic meaning:</span> "
        f"{economic}</div>"
        f"<div style='color:{PALETTE['muted']}; font-size:12px; line-height:1.5;'>"
        f"<span style='color:{PALETTE['accent']}; font-weight:600;'>Actuarial meaning:</span> "
        f"{actuarial}</div>"
        f"</div>",
        unsafe_allow_html=True,
    )


# --------------------------------------------------------------------------- KPI strip
K = _fund_kpis()

mwr_pill = _status_pill(K["mwr"], 0.98, 0.90, higher_is_better=True) if len(ledger) else ""
gini_pill = _status_pill(K["gini"], 0.05, 0.15, higher_is_better=False) if len(ledger) >= 2 else ""
intergen_pill = _status_pill(K["intergen"], 0.95, 0.80, higher_is_better=True) if len(ledger) >= 2 else ""
corridor_pill = (
    _status_pill(K["corridor_pass"], 0.80, 0.50, higher_is_better=True)
    if K["corridor_pass"] is not None else "<span class='pill pill-muted'>NOT RUN</span>"
)

st.markdown(
    "<div class='kpi-strip'>"
    "<div style='display:grid; grid-template-columns: repeat(8, 1fr); gap: 14px;'>"
    + _kpi_cell("MEMBERS", f"{K['members']}", f"{K['cohorts']} cohorts")
    + _kpi_cell("EPV · CONTRIBUTIONS", f"{K['epv_c']:,.0f}", "actuarial present value")
    + _kpi_cell("EPV · BENEFITS",      f"{K['epv_b']:,.0f}", "liability at valuation date")
    + _kpi_cell("SCHEME MWR",          f"{K['mwr']:.2f}",    f"parity = 1.00 {mwr_pill}")
    + _kpi_cell("FUNDED RATIO",        f"{K['funded_ratio']:.1%}", "contrib-to-date / EPV(ben)")
    + _kpi_cell("GINI (MWR)",          f"{K['gini']:.3f}",   f"cohort inequality {gini_pill}")
    + _kpi_cell("INTERGEN INDEX",      f"{K['intergen']:.3f}", f"1.0 = perfect parity {intergen_pill}")
    + _kpi_cell("CORRIDOR PASS",
                f"{K['corridor_pass']:.0%}" if K['corridor_pass'] is not None else "—",
                f"under stochastic stress {corridor_pill}")
    + "</div></div>",
    unsafe_allow_html=True,
)


# --------------------------------------------------------------------------- demo disclaimer
st.markdown(
    "<div class='ribbon' style='border-left:3px solid " + PALETTE["warn"] + ";'>"
    "<span class='pill pill-warn'>DEMO DATA</span> &nbsp; "
    "This terminal runs on illustrative assumptions and a 15-member sample "
    "scheme. Funded ratio, MWR, Gini, intergen index and stress figures are "
    "synthetic &mdash; they demonstrate the mechanism, not a calibrated real "
    "pension scheme. The mortality table is Gompertz&ndash;Makeham, not a "
    "national table."
    "</div>",
    unsafe_allow_html=True,
)


# --------------------------------------------------------------------------- deployment ribbon
_deployment = load_latest()
if _deployment is None:
    st.markdown(
        "<div class='ribbon'>"
        "<span class='pill pill-muted'>OFF-CHAIN ONLY</span> &nbsp; "
        "No deployment detected — run "
        "<code>forge script script/Deploy.s.sol --rpc-url localhost --broadcast</code> "
        "to connect this terminal to a live stack."
        "</div>",
        unsafe_allow_html=True,
    )
else:
    st.markdown(
        "<div class='ribbon'>"
        f"<span class='pill pill-good'>ON-CHAIN CONNECTED</span> &nbsp; "
        f"{len(_deployment.addresses)} contracts deployed · "
        f"owner <code>{_deployment.owner or '—'}</code> · "
        f"source <code>{Path(_deployment.source_path).name}</code>"
        "</div>",
        unsafe_allow_html=True,
    )


# --------------------------------------------------------------------------- tabs
tab_how, tab_over, tab_members, tab_fair, tab_ops, tab_chain = st.tabs(
    [
        "How It Works",
        "Fund Overview",
        "Members & Cohorts",
        "Fairness & Governance",
        "Operations Feed",
        "On-Chain / Contracts",
    ]
)


# =========================================================================== 0 How It Works
with tab_how:
    st.markdown(
        "<div class='section-title'>How Aequitas works</div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        "<div class='section-sub'>A pension scheme re-expressed as a protocol. "
        "The Python engine is the actuarial brain; eight Solidity contracts "
        "are the execution rails. Below is the lifecycle a member, a retiree "
        "and a scheme operator actually experience &mdash; and the map of "
        "who talks to whom.</div>",
        unsafe_allow_html=True,
    )

    st.markdown("**Protocol lifecycle (member journey)**")
    LIFECYCLE = [
        ("1 · JOIN", "Member registers",
         "The scheme records a new member. CohortLedger sorts them into a "
         "5-year birth-year cohort so fairness can be measured generationally.",
         "engine.ledger.register_member &rarr; CohortLedger.registerMember"),
        ("2 · CONTRIBUTE", "Payroll flows in",
         "Each payment mints Pension Income Units (PIUs) &mdash; a stable unit "
         "of promised retirement income, priced by the scheme.",
         "engine.ledger.contribute &rarr; CohortLedger.contribute"),
        ("3 · FAIRNESS CHECK", "Any policy change is gated",
         "FairnessGate holds the baseline EPV per cohort. Every proposal must "
         "keep pairwise \u0394EPV within a corridor \u03b4 &mdash; otherwise it is "
         "rejected, even by majority vote.",
         "engine.fairness.fairness_corridor_check &rarr; FairnessGate.submitAndEvaluate"),
        ("4 · RETIRE", "Member marked retired",
         "VestaRouter orchestrates retirement atomically: pulls reserve from "
         "LongevaPool, funds the BenefitStreamer, starts the income stream.",
         "engine.projection.project_member &rarr; VestaRouter.openRetirement"),
        ("5 · LONGEVA POOL", "Shared longevity risk",
         "A tontine-style pool. When a member dies their shares are burnt, "
         "assets stay, and NAV per share rises for survivors &mdash; exactly "
         "the classical mortality-credit mechanism.",
         "mirrored in engine.simulation &rarr; LongevaPool.releaseMortalityCredit"),
        ("6 · DEATH CONFIRMATION", "Oracle signs the event",
         "MortalityOracle is the authoritative death signal &mdash; "
         "operator-gated, proof-hashed, revocable if filed in error.",
         "trusted input &rarr; MortalityOracle.confirmDeath"),
        ("7 · SURVIVOR STREAM", "Benefit keeps flowing",
         "BenefitStreamer accrues linearly to the retiree and self-stops the "
         "instant the oracle confirms death &mdash; no discretionary cutoff.",
         "engine.projection.benefit_payment &rarr; BenefitStreamer.claim"),
        ("8 · STRESS / BACKSTOP", "Tail-risk release",
         "StressOracle mirrors the Python p95 Gini on chain. BackstopVault "
         "only releases reserve when stress &ge; threshold, capped per call.",
         "engine.fairness_stress.stochastic_cohort_stress &rarr; BackstopVault.release"),
    ]

    for row_start in (0, 4):
        cols = st.columns(4)
        for i in range(4):
            idx = row_start + i
            tag, title, desc, engine_hint = LIFECYCLE[idx]
            with cols[i]:
                st.markdown(
                    f"<div style='background:{PALETTE['panel']}; "
                    f"border:1px solid {PALETTE['edge']}; "
                    f"border-left:3px solid {PALETTE['accent']}; "
                    f"border-radius:8px; padding:12px 14px; height:220px; "
                    f"margin-bottom:10px;'>"
                    f"<div style='color:{PALETTE['accent']}; font-size:11px; "
                    f"font-weight:700; letter-spacing:0.1em; "
                    f"margin-bottom:4px;'>{tag}</div>"
                    f"<div style='color:{PALETTE['text']}; font-size:14px; "
                    f"font-weight:600; margin-bottom:8px;'>{title}</div>"
                    f"<div style='color:{PALETTE['text']}; font-size:12px; "
                    f"line-height:1.45; margin-bottom:8px;'>{desc}</div>"
                    f"<div style='color:{PALETTE['muted']}; font-size:10px; "
                    f"font-family:monospace; line-height:1.3;'>{engine_hint}</div>"
                    f"</div>",
                    unsafe_allow_html=True,
                )

    st.markdown("**Contract interaction map**")
    st.caption(
        "Green nodes are human actors. Blue nodes are Solidity contracts. "
        "Orange is the off-chain Python engine. Solid arrows are direct calls; "
        "dashed arrows are role/gating dependencies."
    )

    dot = f"""
    digraph Aequitas {{
        rankdir=LR;
        bgcolor="{PALETTE['bg']}";
        pad=0.3;
        nodesep=0.35;
        ranksep=0.55;
        node [style="rounded,filled", fontname="Helvetica", fontsize=11,
              color="{PALETTE['edge']}", fontcolor="{PALETTE['text']}"];
        edge [color="{PALETTE['muted']}", fontcolor="{PALETTE['muted']}",
              fontname="Helvetica", fontsize=9];

        // human actors (green)
        Member    [label="Member",          fillcolor="#052e2b", color="{PALETTE['good']}", fontcolor="{PALETTE['good']}"];
        Retiree   [label="Retiree",         fillcolor="#052e2b", color="{PALETTE['good']}", fontcolor="{PALETTE['good']}"];
        Operator  [label="Operator",        fillcolor="#052e2b", color="{PALETTE['good']}", fontcolor="{PALETTE['good']}"];
        Guardian  [label="Guardian",        fillcolor="#052e2b", color="{PALETTE['good']}", fontcolor="{PALETTE['good']}"];
        Reporter  [label="Oracle reporter", fillcolor="#052e2b", color="{PALETTE['good']}", fontcolor="{PALETTE['good']}"];

        // off-chain brain (amber)
        Engine [label="Python actuarial engine\\n(EPVs, Gini, stress)",
                fillcolor="#2a1c05", color="{PALETTE['warn']}", fontcolor="{PALETTE['warn']}"];

        // contracts (cyan)
        CohortLedger    [fillcolor="#0c2030", color="{PALETTE['accent']}", fontcolor="{PALETTE['accent']}"];
        FairnessGate    [fillcolor="#0c2030", color="{PALETTE['accent']}", fontcolor="{PALETTE['accent']}"];
        MortalityOracle [fillcolor="#0c2030", color="{PALETTE['accent']}", fontcolor="{PALETTE['accent']}"];
        LongevaPool     [fillcolor="#0c2030", color="{PALETTE['accent']}", fontcolor="{PALETTE['accent']}"];
        VestaRouter     [fillcolor="#0c2030", color="{PALETTE['accent']}", fontcolor="{PALETTE['accent']}"];
        BenefitStreamer [fillcolor="#0c2030", color="{PALETTE['accent']}", fontcolor="{PALETTE['accent']}"];
        StressOracle    [fillcolor="#0c2030", color="{PALETTE['accent']}", fontcolor="{PALETTE['accent']}"];
        BackstopVault   [fillcolor="#0c2030", color="{PALETTE['accent']}", fontcolor="{PALETTE['accent']}"];

        // edges
        Member    -> CohortLedger    [label="register, contribute"];
        Member    -> LongevaPool     [label="deposit"];
        Engine    -> FairnessGate    [label="setBaseline, proposal"];
        Engine    -> StressOracle    [label="stress summary"];
        Reporter  -> MortalityOracle [label="confirmDeath"];
        Reporter  -> StressOracle    [label="update level"];
        Operator  -> VestaRouter     [label="openRetirement"];
        VestaRouter -> LongevaPool     [label="payTo"];
        VestaRouter -> BenefitStreamer [label="fund, startStream"];
        MortalityOracle -> BenefitStreamer [label="halts stream", style=dashed];
        MortalityOracle -> LongevaPool     [label="burns shares", style=dashed];
        StressOracle    -> BackstopVault   [label="gates release", style=dashed];
        Guardian  -> BackstopVault   [label="release"];
        Retiree   -> BenefitStreamer [label="claim"];
    }}
    """
    st.graphviz_chart(dot, use_container_width=True)

    st.caption(
        "Reading the map: the Python engine never pays anyone &mdash; it only "
        "publishes numbers (baseline, stress). Money only moves through the "
        "contracts, and every movement is role-gated."
    )


# =========================================================================== 1 Fund Overview
with tab_over:
    st.markdown("<div class='section-title'>Fund overview</div>", unsafe_allow_html=True)
    st.markdown(
        "<div class='section-sub'>A single-page read on the scheme's health: "
        "who is in, what has been promised, how the fund is projected to evolve, "
        "and where stress is concentrated across cohorts.</div>",
        unsafe_allow_html=True,
    )

    if len(ledger) == 0:
        st.info("No members yet. Click **Load demo data** in the sidebar to seed the terminal.")
    else:
        # ---- top row: projection chart + signal panel
        col_main, col_side = st.columns([3, 2])

        fund_df = project_fund(
            ledger.get_all_members(),
            valuation_year=ledger.valuation_year,
            salary_growth=ledger.salary_growth,
            investment_return=ledger.investment_return,
            discount_rate=ledger.discount_rate,
            horizon=60,
        )

        with col_main:
            st.markdown("**Aggregate fund projection (deterministic)**")
            if not fund_df.empty:
                long = fund_df.melt(
                    id_vars="year",
                    value_vars=["fund_value", "contributions", "benefit_payments"],
                    var_name="series", value_name="amount",
                )
                chart = (
                    alt.Chart(long)
                    .mark_line(strokeWidth=2)
                    .encode(
                        x=alt.X("year:Q", title=None),
                        y=alt.Y("amount:Q", title="Amount", stack=None),
                        color=alt.Color("series:N", legend=alt.Legend(title=None, orient="top")),
                        tooltip=["year", "series", alt.Tooltip("amount:Q", format=",.0f")],
                    )
                    .properties(height=300)
                )
                st.altair_chart(chart, use_container_width=True)

        with col_side:
            st.markdown("**Signals**")
            cv = ledger.cohort_valuation()
            mwrs = {c: cv[c]["money_worth_ratio"] for c in cv}
            # highlight youngest + oldest cohort MWRs
            if mwrs:
                oldest, youngest = min(mwrs), max(mwrs)
                sig_df = pd.DataFrame([
                    {"signal": "Oldest cohort MWR",
                     "value": f"{mwrs[oldest]:.2f}", "cohort": oldest},
                    {"signal": "Youngest cohort MWR",
                     "value": f"{mwrs[youngest]:.2f}", "cohort": youngest},
                    {"signal": "MWR range (max − min)",
                     "value": f"{max(mwrs.values()) - min(mwrs.values()):.2f}", "cohort": "—"},
                    {"signal": "Scheme funded ratio",
                     "value": f"{K['funded_ratio']:.1%}", "cohort": "—"},
                    {"signal": "Stress (last p95 Gini)",
                     "value": (f"{K['stress_level']:.3f}" if K['stress_level'] is not None else "not run"),
                     "cohort": "—"},
                ])
                st.dataframe(sig_df, use_container_width=True, hide_index=True)

            if event_log and len(event_log) > 0:
                st.markdown("**Latest operations**")
                last_events = list(event_log)[-5:]
                ev_df = pd.DataFrame([
                    {"seq": e.seq, "event": e.event_type,
                     "hash": e.hash[:10] + "…"}
                    for e in reversed(last_events)
                ])
                st.dataframe(ev_df, use_container_width=True, hide_index=True)

        # ---- second row: cohort bars
        bar_col1, bar_col2 = st.columns(2)
        with bar_col1:
            st.markdown("**EPV(benefits) by cohort**")
            cv_df = (
                pd.DataFrame([
                    {"cohort": int(c),
                     "epv_benefits": float(cv[c]["epv_benefits"]),
                     "epv_contributions": float(cv[c]["epv_contributions"]),
                     "mwr": float(cv[c]["money_worth_ratio"])}
                    for c in cv
                ])
                .sort_values("cohort").reset_index(drop=True)
            )
            bc = (
                alt.Chart(cv_df)
                .mark_bar()
                .encode(
                    x=alt.X("cohort:O", title="Cohort (birth year bucket)"),
                    y=alt.Y("epv_benefits:Q", title="EPV benefits"),
                    tooltip=["cohort",
                             alt.Tooltip("epv_benefits:Q", format=",.0f"),
                             alt.Tooltip("epv_contributions:Q", format=",.0f"),
                             alt.Tooltip("mwr:Q", format=".2f")],
                    color=alt.value(PALETTE["accent"]),
                )
                .properties(height=220)
            )
            st.altair_chart(bc, use_container_width=True)

        with bar_col2:
            st.markdown("**MWR by cohort (parity = 1.00)**")
            mwr_chart = (
                alt.Chart(cv_df)
                .mark_bar()
                .encode(
                    x=alt.X("cohort:O", title=None),
                    y=alt.Y("mwr:Q", title="Money's worth ratio",
                            scale=alt.Scale(domain=[0, max(1.2, cv_df["mwr"].max() * 1.1)])),
                    color=alt.condition(
                        "datum.mwr >= 0.95 && datum.mwr <= 1.05",
                        alt.value(PALETTE["good"]),
                        alt.value(PALETTE["warn"]),
                    ),
                    tooltip=["cohort", alt.Tooltip("mwr:Q", format=".3f")],
                )
                .properties(height=220)
            )
            rule = alt.Chart(pd.DataFrame({"y": [1.0]})).mark_rule(
                color=PALETTE["muted"], strokeDash=[4, 4]
            ).encode(y="y:Q")
            st.altair_chart(mwr_chart + rule, use_container_width=True)

        with st.expander("Show projection data"):
            st.dataframe(fund_df, use_container_width=True, hide_index=True)


# =========================================================================== 2 Members & Cohorts
with tab_members:
    st.markdown("<div class='section-title'>Members &amp; cohorts</div>", unsafe_allow_html=True)
    st.markdown(
        "<div class='section-sub'>The member register, per-member actuarial "
        "valuation and projections. Registration and contribution controls sit "
        "below the dashboard so they do not crowd the primary read.</div>",
        unsafe_allow_html=True,
    )

    if len(ledger) == 0:
        st.info("Load demo data in the sidebar to populate the register.")
    else:
        # roster + cohort bar together
        members = ledger.get_all_members()
        df = pd.DataFrame([m.to_dict() for m in members])
        df["age"] = ledger.valuation_year - df["birth_year"]

        top_l, top_r = st.columns([3, 2])
        with top_l:
            st.markdown("**Member roster**")
            st.dataframe(df, use_container_width=True, hide_index=True, height=280)
        with top_r:
            st.markdown("**Cohort contribution totals**")
            if ledger.cohort_aggregate_contrib:
                coh_df = (
                    pd.DataFrame(
                        [{"cohort": int(k), "total_contributions": float(v)}
                         for k, v in ledger.cohort_aggregate_contrib.items()]
                    )
                    .sort_values("cohort").reset_index(drop=True)
                )
                chart = (
                    alt.Chart(coh_df).mark_bar()
                    .encode(
                        x=alt.X("cohort:O", title="Cohort"),
                        y=alt.Y("total_contributions:Q", title="Contributions"),
                        tooltip=["cohort",
                                 alt.Tooltip("total_contributions:Q", format=",.0f")],
                        color=alt.value(PALETTE["accent"]),
                    )
                    .properties(height=280)
                )
                st.altair_chart(chart, use_container_width=True)

        # ---- per-member valuation
        st.markdown("**Per-member actuarial valuation**")
        st.caption(
            "EPV = Σ v^t · p_x(t) · CF_t using a Gompertz–Makeham life table "
            "and an annuity-due factor. Money's Worth Ratio = EPV(benefits) / "
            "EPV(contributions)."
        )
        valuations = ledger.value_all()
        val_df = pd.DataFrame([v.__dict__ for v in valuations]).merge(
            pd.DataFrame([{"wallet": m.wallet, "cohort": m.cohort}
                          for m in ledger]),
            on="wallet",
        )
        st.dataframe(
            val_df.style.format({
                "epv_contributions": "{:,.0f}",
                "epv_benefits": "{:,.0f}",
                "money_worth_ratio": "{:.2f}",
                "projected_annual_benefit": "{:,.0f}",
                "replacement_ratio": "{:.2%}",
            }),
            use_container_width=True, height=260,
        )

        # ---- projection + Monte-Carlo drilldown
        st.markdown("**Member drill-down — projection & stochastic outcomes**")
        wallets = [m.wallet for m in ledger]
        dcol1, dcol2 = st.columns([1, 3])
        with dcol1:
            w = st.selectbox("Member", wallets, key="drill_member")
            n_paths = st.number_input("MC paths", 200, 20_000, 2_000, 200, key="drill_paths")
            sigma = st.slider("Return σ", 0.01, 0.30, 0.10, 0.01, key="drill_sigma")
            seed = st.number_input("Seed", value=42, step=1, key="drill_seed")
        member = ledger.get_member_summary(w)
        proj_df = project_member(
            member,
            valuation_year=ledger.valuation_year,
            salary_growth=ledger.salary_growth,
            investment_return=ledger.investment_return,
            discount_rate=ledger.discount_rate,
            horizon=60,
        )
        mc_result = simulate_member(
            member,
            valuation_year=ledger.valuation_year,
            n_paths=int(n_paths),
            mu=ledger.investment_return,
            sigma=float(sigma),
            salary_growth=ledger.salary_growth,
            discount_rate=ledger.discount_rate,
            seed=int(seed),
        )

        with dcol2:
            retired_df = proj_df[proj_df.phase == "retired"]
            first_benefit = retired_df["benefit_payment"].iloc[0] if not retired_df.empty else 0.0
            accum_df = proj_df[proj_df.phase == "accumulation"]
            peak = accum_df["fund_value"].max() if not accum_df.empty else 0.0
            m1, m2, m3 = st.columns(3)
            m1.metric("Current age", member.age(ledger.valuation_year))
            m2.metric("Annual benefit @ retirement", f"{first_benefit:,.0f}")
            m3.metric("Fund @ retirement (det.)", f"{peak:,.0f}")

            proj_long = proj_df.melt(
                id_vars="year",
                value_vars=["fund_value", "contribution", "benefit_payment"],
                var_name="series", value_name="amount",
            )
            proj_chart = (
                alt.Chart(proj_long).mark_line(strokeWidth=2)
                .encode(
                    x=alt.X("year:Q", title=None),
                    y=alt.Y("amount:Q", title="Amount", stack=None),
                    color=alt.Color("series:N", legend=alt.Legend(title=None, orient="top")),
                    tooltip=["year", "series",
                             alt.Tooltip("amount:Q", format=",.0f")],
                )
                .properties(height=240)
            )
            st.altair_chart(proj_chart, use_container_width=True)

        mc1, mc2 = st.columns(2)
        with mc1:
            st.markdown("**Monte-Carlo percentiles**")
            st.dataframe(
                mc_result["percentiles"].style.format({
                    "fund_at_retirement": "{:,.0f}",
                    "annual_benefit": "{:,.0f}",
                    "replacement_ratio": "{:.2%}",
                }),
                use_container_width=True,
            )
        with mc2:
            st.markdown("**Fan chart of fund value (percentiles)**")
            mc_long = mc_result["time_series"].reset_index().melt(
                id_vars="year", var_name="series", value_name="amount",
            )
            fan = (
                alt.Chart(mc_long).mark_line(strokeWidth=2)
                .encode(
                    x=alt.X("year:Q", title=None),
                    y=alt.Y("amount:Q", title="Fund value", stack=None),
                    color=alt.Color("series:N", legend=alt.Legend(title=None, orient="top")),
                    tooltip=["year", "series",
                             alt.Tooltip("amount:Q", format=",.0f")],
                )
                .properties(height=240)
            )
            st.altair_chart(fan, use_container_width=True)

        # ---- scheme-level MC aggregate
        with st.expander("Scheme-level aggregate fan (Monte Carlo)"):
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
                agg_long = agg.reset_index().melt(
                    id_vars="year", var_name="series", value_name="amount",
                )
                st.altair_chart(
                    alt.Chart(agg_long).mark_line(strokeWidth=2).encode(
                        x=alt.X("year:Q", title=None),
                        y=alt.Y("amount:Q", title=None, stack=None),
                        color=alt.Color("series:N",
                                        legend=alt.Legend(title=None, orient="top")),
                    ).properties(height=260),
                    use_container_width=True,
                )

        # ---- mortality table (reference)
        with st.expander("Mortality reference — life expectancy & annuity factors"):
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

        # ---- registration and contribution forms (tucked under expanders)
        with st.expander("Register a new member"):
            with st.form("register_form"):
                c1, c2, c3 = st.columns(3)
                with c1:
                    wallet = st.text_input("Wallet / Member ID")
                    birth_year = st.number_input("Birth year", 1940, 2010, 1975, 1)
                with c2:
                    salary = st.number_input("Salary", 0.0, value=50000.0, step=1000.0)
                    contribution_rate = st.slider("Contribution rate", 0.0, 0.25, 0.10, 0.01)
                with c3:
                    retirement_age = st.number_input("Retirement age", 55, 75, 65, 1)
                    sex = st.selectbox("Sex (mortality loading)", ["U", "M", "F"], index=0)
                submitted = st.form_submit_button("Register")
                if submitted:
                    try:
                        if not wallet.strip():
                            raise ValueError("Wallet / Member ID cannot be empty")
                        ledger.register_member(
                            wallet=wallet.strip(), birth_year=int(birth_year),
                            salary=float(salary),
                            contribution_rate=float(contribution_rate),
                            retirement_age=int(retirement_age), sex=sex,
                        )
                        event_log.append(
                            "member_registered",
                            wallet=wallet.strip(), birth_year=int(birth_year),
                        )
                        st.success(f"Registered {wallet}")
                    except Exception as exc:
                        st.error(str(exc))

        with st.expander("Record a contribution"):
            with st.form("contribution_form"):
                c1, c2 = st.columns([2, 1])
                contrib_wallet = c1.text_input("Wallet / Member ID")
                amount = c2.number_input("Amount", 0.0, value=1000.0, step=100.0)
                submitted = st.form_submit_button("Contribute")
                if submitted:
                    try:
                        if not contrib_wallet.strip():
                            raise ValueError("Wallet / Member ID cannot be empty")
                        piu = ledger.contribute(contrib_wallet.strip(), float(amount))
                        event_log.append(
                            "contribution_recorded",
                            wallet=contrib_wallet.strip(),
                            amount=float(amount),
                            piu_minted=float(piu),
                        )
                        st.success(f"PIUs minted: {piu:.2f}")
                    except Exception as exc:
                        st.error(str(exc))


# =========================================================================== 3 Fairness & Governance
with tab_fair:
    st.markdown("<div class='section-title'>Fairness &amp; governance</div>", unsafe_allow_html=True)
    st.markdown(
        "<div class='section-sub'>The heart of Aequitas: is every generation "
        "treated fairly? We measure deviation from parity (MWR = 1.0), "
        "dispersion across cohorts (Gini), and pass-rate of the "
        "fairness corridor under stochastic shocks.</div>",
        unsafe_allow_html=True,
    )

    if len(ledger) < 2:
        st.info("Need ≥2 members across cohorts. Load demo data in the sidebar.")
    else:
        cv = ledger.cohort_valuation()
        mwrs = {c: cv[c]["money_worth_ratio"] for c in cv}
        disp = mwr_dispersion(mwrs)

        # ---- fairness KPIs
        f1, f2, f3, f4 = st.columns(4)
        f1.metric("MWR min → max", f"{disp['min']:.2f} → {disp['max']:.2f}")
        f2.metric("MWR std dev", f"{disp['std']:.3f}")
        f3.metric("Gini (MWR)", f"{K['gini']:.3f}")
        f4.metric("Intergenerational index", f"{K['intergen']:.3f}")

        mwr_df = (
            pd.DataFrame([{"cohort": int(k), "mwr": float(v)} for k, v in mwrs.items()])
            .sort_values("cohort").reset_index(drop=True)
        )
        bar = (
            alt.Chart(mwr_df).mark_bar().encode(
                x=alt.X("cohort:O", title="Cohort"),
                y=alt.Y("mwr:Q", title="Money's worth ratio",
                        scale=alt.Scale(domain=[0, max(1.2, mwr_df["mwr"].max() * 1.1)])),
                color=alt.condition(
                    "datum.mwr >= 0.95 && datum.mwr <= 1.05",
                    alt.value(PALETTE["good"]),
                    alt.value(PALETTE["warn"]),
                ),
                tooltip=["cohort", alt.Tooltip("mwr:Q", format=".3f")],
            ).properties(height=260)
        )
        rule = alt.Chart(pd.DataFrame({"y": [1.0]})).mark_rule(
            color=PALETTE["muted"], strokeDash=[4, 4]
        ).encode(y="y:Q")
        st.altair_chart(bar + rule, use_container_width=True)

        # ---- governance sandbox
        st.markdown("**Governance sandbox — evaluate a proposal**")
        st.caption(
            "Propose a benefit multiplier per cohort (1.00 = no change). "
            "Aequitas evaluates the proposal against the fairness corridor and "
            "writes the decision to the audit chain."
        )
        cohorts = sorted(cv.keys())
        cols = st.columns(min(len(cohorts), 6) or 1)
        multipliers: dict[int, float] = {}
        for i, cohort in enumerate(cohorts):
            col = cols[i % len(cols)]
            multipliers[cohort] = col.slider(
                f"Cohort {cohort}", 0.70, 1.30, 1.00, 0.01, key=f"gov_mult_{cohort}",
            )
        dcol1, dcol2 = st.columns(2)
        delta = dcol1.slider("Fairness corridor δ", 0.01, 0.25, 0.05, 0.01)
        name = dcol2.text_input("Proposal name", "Cohort adjustment")

        if st.button("Evaluate proposal", type="primary"):
            outcome = evaluate_proposal(cv, multipliers, delta=delta)
            event_log.append(
                "proposal_evaluated",
                name=name,
                multipliers={int(k): float(v) for k, v in multipliers.items()},
                passes=bool(outcome["passes"]),
                gini_before=round(outcome["gini_before"], 4),
                gini_after=round(outcome["gini_after"], 4),
                index_before=round(outcome["index_before"], 4),
                index_after=round(outcome["index_after"], 4),
            )
            o1, o2, o3 = st.columns(3)
            o1.metric("Gini MWR", f"{outcome['gini_after']:.3f}",
                      delta=f"{outcome['gini_after'] - outcome['gini_before']:+.3f}")
            o2.metric("Intergen index", f"{outcome['index_after']:.3f}",
                      delta=f"{outcome['index_after'] - outcome['index_before']:+.3f}")
            if outcome["passes"]:
                o3.markdown("<br><span class='pill pill-good'>CORRIDOR PASSES</span>",
                            unsafe_allow_html=True)
            else:
                o3.markdown("<br><span class='pill pill-bad'>CORRIDOR FAILS</span>",
                            unsafe_allow_html=True)

            compare_df = (
                pd.DataFrame({
                    "cohort": list(outcome["mwr_before"].keys()),
                    "mwr_before": list(outcome["mwr_before"].values()),
                    "mwr_after": list(outcome["mwr_after"].values()),
                })
                .sort_values("cohort").reset_index(drop=True)
                .melt(id_vars="cohort", var_name="series", value_name="mwr")
            )
            cmp_chart = (
                alt.Chart(compare_df).mark_bar().encode(
                    x=alt.X("cohort:O", title="Cohort"),
                    xOffset="series:N",
                    y=alt.Y("mwr:Q", title="MWR"),
                    color=alt.Color("series:N",
                                    legend=alt.Legend(title=None, orient="top")),
                    tooltip=["cohort", "series",
                             alt.Tooltip("mwr:Q", format=".3f")],
                ).properties(height=260)
            )
            st.altair_chart(cmp_chart + rule, use_container_width=True)

        # ---- fairness stress
        st.markdown("**Stochastic fairness stress**")
        st.caption(
            "One-factor cohort shock: m_c(s) = 1 + β_c · F(s) + ε_c(s). "
            "We sample S scenarios, recompute per-cohort MWRs and report the "
            "worst-case Gini, the intergenerational index and how often the "
            "corridor rule passes."
        )
        s1, s2, s3 = st.columns(3)
        n_scen = s1.number_input("Scenarios", 200, 20_000, 2_000, 200, key="stress_n")
        factor_sigma = s2.slider("Macro σ_F", 0.0, 0.30, 0.10, 0.01, key="stress_f")
        idio_sigma = s3.slider("Idiosyncratic σ_ε", 0.0, 0.15, 0.03, 0.005, key="stress_e")
        s4, s5, s6 = st.columns(3)
        gen_slope = s4.slider("Generational slope |β_max|", 0.0, 1.0, 0.50, 0.05,
                              key="stress_b")
        corridor_delta = s5.slider("Corridor δ", 0.01, 0.20, 0.05, 0.01,
                                   key="stress_d")
        poor_thr = s6.slider("Youngest-poor threshold (MWR)", 0.50, 1.00, 0.90, 0.05,
                             key="stress_t")
        seed = st.number_input("Seed", value=42, step=1, key="stress_seed")

        if st.button("Run stress", key="run_stress"):
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
            st.session_state.cached_stress = result
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

        result = st.session_state.cached_stress
        if result is not None:
            k1, k2, k3, k4 = st.columns(4)
            k1.metric("Mean Gini", f"{result['mean_gini']:.3f}")
            k2.metric("p95 Gini (worst)", f"{result['p95_gini']:.3f}")
            k3.metric("Corridor pass rate", f"{result['corridor_pass_rate']:.1%}")
            k4.metric(
                f"P(MWR<{result['youngest_poor_threshold']:.2f} on youngest)",
                f"{result['youngest_poor_rate']:.1%}",
            )

            left, right = st.columns(2)
            with left:
                st.markdown("Cohort betas used")
                beta_df = (
                    pd.DataFrame([{"cohort": int(c), "beta": float(b)}
                                  for c, b in result["betas"].items()])
                    .sort_values("cohort").reset_index(drop=True)
                )
                st.altair_chart(
                    alt.Chart(beta_df).mark_bar().encode(
                        x=alt.X("cohort:O", title="Cohort"),
                        y=alt.Y("beta:Q", title="β"),
                        color=alt.condition(
                            "datum.beta >= 0",
                            alt.value(PALETTE["warn"]),
                            alt.value(PALETTE["accent"]),
                        ),
                    ).properties(height=220),
                    use_container_width=True,
                )
            with right:
                st.markdown("Worst-affected cohort frequency")
                worst_df = (
                    pd.DataFrame([{"cohort": int(c), "freq": float(f)}
                                  for c, f in result["worst_cohort_freq"].items()])
                    .sort_values("cohort").reset_index(drop=True)
                )
                st.altair_chart(
                    alt.Chart(worst_df).mark_bar().encode(
                        x=alt.X("cohort:O", title="Cohort"),
                        y=alt.Y("freq:Q", title="P(worst cohort)",
                                axis=alt.Axis(format=".0%")),
                        color=alt.value(PALETTE["bad"]),
                        tooltip=["cohort",
                                 alt.Tooltip("freq:Q", format=".1%")],
                    ).properties(height=220),
                    use_container_width=True,
                )

            with st.expander("Gini distribution across scenarios"):
                gdf = pd.DataFrame({"gini": result["gini_series"]})
                st.altair_chart(
                    alt.Chart(gdf).mark_bar().encode(
                        x=alt.X("gini:Q", bin=alt.Bin(maxbins=30)),
                        y=alt.Y("count()", title="scenarios"),
                        color=alt.value(PALETTE["accent"]),
                    ).properties(height=220),
                    use_container_width=True,
                )

            with st.expander("Stress summary frame"):
                st.dataframe(summary_frame(result),
                             use_container_width=True, hide_index=True)

        # ---- legacy MVP corridor demo
        with st.expander("MVP corridor check (stylised scenario)"):
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
                result_mvp = fairness_corridor_check(
                    cohort_epvs_old, cohort_epvs_new, epv_bench, delta=0.05,
                )
                c1, c2 = st.columns(2)
                with c1:
                    st.write("Old EPVs", cohort_epvs_old)
                    st.write("New EPVs", {k: round(v, 2) for k, v in cohort_epvs_new.items()})
                with c2:
                    st.metric("Max pairwise deviation", f"{result_mvp['max_deviation']:.2%}")
                    st.metric("Allowed", f"{result_mvp['delta_limit']:.0%}")
                    if result_mvp["passes"]:
                        st.success("PASSES")
                    else:
                        st.error(f"FAILS — worst pair {result_mvp['worst_pair']}")
            else:
                st.info("≥3 cohorts needed for the MVP corridor demo.")


# =========================================================================== 4 Operations Feed
with tab_ops:
    st.markdown("<div class='section-title'>Operations feed</div>", unsafe_allow_html=True)
    st.markdown(
        "<div class='section-sub'>An append-only, hash-chained log of every "
        "governance-relevant action: member registered, contribution recorded, "
        "proposal evaluated, stress run, bridge hand-off. This is the "
        "audit-ready provenance record of the scheme.</div>",
        unsafe_allow_html=True,
    )

    if len(event_log) == 0:
        st.info("No events recorded yet. Load demo data, run a stress, or evaluate a proposal.")
    else:
        verified = event_log.verify()
        (st.success if verified else st.error)(
            f"Chain integrity: {'VERIFIED' if verified else 'TAMPERED'} — "
            f"{len(event_log)} events"
        )

        # Pretty, sentence-style rows
        pretty_df = pd.DataFrame([
            {
                "seq": e.seq,
                "event": _pretty_event(e),
                "type": e.event_type,
                "hash": e.hash[:10] + "…",
            }
            for e in event_log
        ])

        type_df = pretty_df["type"].value_counts().reset_index()
        type_df.columns = ["event_type", "count"]

        feed_left, feed_right = st.columns([3, 2])
        with feed_left:
            st.markdown("**Event timeline (newest first)**")
            st.dataframe(
                pretty_df.iloc[::-1],
                use_container_width=True, hide_index=True, height=460,
                column_config={
                    "seq": st.column_config.NumberColumn("#", width="small"),
                    "event": st.column_config.TextColumn("Event", width="large"),
                    "type": st.column_config.TextColumn("Type", width="medium"),
                    "hash": st.column_config.TextColumn("Hash", width="small"),
                },
            )
        with feed_right:
            st.markdown("**Event types**")
            st.altair_chart(
                alt.Chart(type_df).mark_bar().encode(
                    y=alt.Y("event_type:N", sort="-x", title=None),
                    x=alt.X("count:Q", title="Events"),
                    color=alt.value(PALETTE["accent"]),
                    tooltip=["event_type", "count"],
                ).properties(height=320),
                use_container_width=True,
            )
            st.caption(
                "Every row is hash-linked to the previous one. "
                "Mirrors the `emit`-based audit trail on the Solidity side."
            )

        with st.expander("Raw hash-chain data (technical appendix)"):
            raw_df = pd.DataFrame([
                {
                    "seq": e.seq,
                    "event_type": e.event_type,
                    "data": e.data,
                    "hash": e.hash,
                    "prev_hash": e.prev_hash,
                }
                for e in event_log
            ])
            st.dataframe(raw_df, use_container_width=True, hide_index=True)


# =========================================================================== 5 On-Chain / Contracts
with tab_chain:
    st.markdown("<div class='section-title'>On-chain / contracts</div>", unsafe_allow_html=True)
    st.markdown(
        "<div class='section-sub'>Solidity execution layer: eight contracts "
        "grouped into four phases — EquiGen (CohortLedger + FairnessGate), "
        "Longeva (MortalityOracle + LongevaPool), Vesta (VestaRouter + "
        "BenefitStreamer), Astra (StressOracle + BackstopVault). "
        "Every governance action below is serialised to the exact on-chain "
        "call the Python bridge would emit.</div>",
        unsafe_allow_html=True,
    )

    if _deployment is None:
        st.warning(
            "No deployment detected. The terminal is running off-chain only — "
            "payload previews are still valid, just not wired to a live "
            "endpoint. Deploy with `forge script script/Deploy.s.sol`."
        )
    else:
        st.markdown("**Deployed addresses**")
        st.dataframe(
            pd.DataFrame([
                {"contract": k, "address": v}
                for k, v in _deployment.addresses.items()
            ]),
            use_container_width=True, hide_index=True,
        )

    if len(ledger) == 0:
        st.info("Load demo data in the sidebar to see bridged calls.")
    else:
        calls = ledger_to_chain_calls(ledger)
        cv = ledger.cohort_valuation()

        # ------------------------------------------------------ 1. Register + contribute
        _action_card(
            name="Register &amp; contribute",
            actor="Member (via payroll)",
            target="CohortLedger",
            economic=(
                "A new member joins and each contribution mints Pension "
                "Income Units (PIUs). PIUs are the scheme&rsquo;s internal "
                "claim token."
            ),
            actuarial=(
                "`register_member` populates demographics (birth year &rarr; "
                "5-year cohort bucket). `contribute` increments "
                "`total_contributions` and mints PIUs at the published price."
            ),
        )
        st.caption(f"{len(calls)} bridged calls replay the current ledger on chain.")
        with st.expander("Raw bridged payloads &mdash; register + contribute"):
            st.json(calls_to_json(calls[:10]))
            if len(calls) > 10:
                st.caption(f"(showing first 10 of {len(calls)})")

        # ------------------------------------------------------ 2. setBaseline
        _action_card(
            name="Publish baseline",
            actor="Python actuarial engine",
            target="FairnessGate",
            economic=(
                "Freezes the current EPV per cohort as the governance "
                "reference point. Future proposals will be judged against this."
            ),
            actuarial=(
                "`cohort_valuation()` vector scaled to 1e18 fixed-point and "
                "typed as (uint16 cohort, int256 EPV). This is the "
                "denominator in the corridor test."
            ),
        )
        with st.expander("Raw bridged payload &mdash; setBaseline"):
            st.json(encode_baseline(cv).as_dict())

        # ------------------------------------------------------ 3. Proposal
        _action_card(
            name="Submit proposal",
            actor="Governance (operator role)",
            target="FairnessGate",
            economic=(
                "Propose a cohort-by-cohort benefit multiplier. The corridor "
                "rule accepts or rejects on chain &mdash; majority vote cannot "
                "override it."
            ),
            actuarial=(
                "Tests max &#8214;&Delta;EPV&#7522; &minus; &Delta;EPV&#11388;&#8214; / "
                "benchmark &le; &delta; across every cohort pair &mdash; "
                "identical arithmetic to `fairness_corridor_check` in Python."
            ),
        )
        cohorts = sorted(cv.keys())
        prop_col1, prop_col2 = st.columns([2, 1])
        with prop_col1:
            prop_name = st.text_input(
                "Proposal name", value="Trim youngest cohort by 3%",
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
                    f"{c} ×", value=0.97 if c == cohorts[-1] else 1.0,
                    min_value=0.5, max_value=1.5, step=0.01,
                    key=f"bridge_mult_{c}",
                )
        proposal = Proposal(
            name=prop_name, description="Bridge preview",
            multipliers=mult_inputs,
        )
        with st.expander("Raw bridged payload &mdash; submitAndEvaluate"):
            st.json(encode_proposal(proposal, cv, delta=delta_pct / 100.0).as_dict())

        chain_cols = st.columns(2)

        # ------------------------------------------------------ 4. Pool deposit
        with chain_cols[0]:
            _action_card(
                name="Fund the longevity pool",
                actor="Depositor (sponsor / treasury)",
                target="LongevaPool",
                economic=(
                    "Top up the shared reserve that finances retirement "
                    "income. Deposits receive shares at the current NAV."
                ),
                actuarial=(
                    "Backs future annuity liabilities. Assets remain when a "
                    "member dies &mdash; NAV per share rises, which is the "
                    "classical mortality credit."
                ),
            )
            pool_wallet = st.text_input(
                "Depositor wallet", value=sorted(ledger.members.keys())[0],
                key="bridge_pool_wallet",
            )
            pool_amount = st.number_input(
                "Amount (ETH)", value=10.0, min_value=0.01, step=1.0,
                key="bridge_pool_amount",
            )
            with st.expander("Raw bridged payload &mdash; LongevaPool.deposit"):
                st.json(encode_pool_deposit(pool_wallet, pool_amount).as_dict())

            # -------------------------------------------------- 5. Open retirement
            _action_card(
                name="Open retirement",
                actor="Operator",
                target="VestaRouter &rarr; LongevaPool + BenefitStreamer",
                economic=(
                    "Moves the member from accumulation into payout. Reserve "
                    "leaves the pool, funds the streamer, stream starts."
                ),
                actuarial=(
                    "B_annual comes from `project_member` / "
                    "`value_member`. Atomic `payTo &rarr; fund &rarr; "
                    "startStream` prevents a half-opened retirement."
                ),
            )
            ret_wallet = st.text_input(
                "Retiree wallet", value=sorted(ledger.members.keys())[0],
                key="bridge_ret_wallet",
            )
            ret_funding = st.number_input(
                "Funding (ETH)", value=10.0, min_value=0.01, step=1.0,
                key="bridge_ret_funding",
            )
            ret_annual = st.number_input(
                "Annual benefit (ETH)", value=1.2, min_value=0.01, step=0.1,
                key="bridge_ret_annual",
            )
            with st.expander("Raw bridged payload &mdash; VestaRouter.openRetirement"):
                st.json(
                    encode_open_retirement(ret_wallet, ret_funding, ret_annual).as_dict()
                )

        with chain_cols[1]:
            # -------------------------------------------------- 6. Stress update
            _action_card(
                name="Publish stress signal",
                actor="Reporter (oracle role)",
                target="StressOracle",
                economic=(
                    "Tells the on-chain system how bad the environment looks. "
                    "Nothing moves by itself &mdash; downstream gates read "
                    "this number."
                ),
                actuarial=(
                    "A 1e18-scaled summary of the Monte-Carlo stress: "
                    "typically p95 Gini crossing the corridor-pass threshold. "
                    "Comes with a bytes32 reason code and SHA-256 data hash."
                ),
            )
            stress_level = st.slider(
                "Stress level", 0.0, 1.0, 0.25, 0.05, key="bridge_stress_level",
            )
            reason = st.text_input(
                "Reason (≤31 chars)", value="p95_gini>threshold", key="bridge_reason",
            )
            summary = {
                "n_members": len(ledger), "n_cohorts": len(cv),
                "stress_level": stress_level,
            }
            with st.expander("Raw bridged payload &mdash; StressOracle.updateStressLevel"):
                st.json(encode_stress_update(stress_level, reason, str(summary)).as_dict())

            # -------------------------------------------------- 7. Backstop
            _action_card(
                name="Seed &amp; release the backstop",
                actor="Depositor &rarr; Guardian",
                target="BackstopVault",
                economic=(
                    "A reserve vault that can only be tapped in stress. "
                    "Removes discretionary bailout without removing human "
                    "oversight (guardian multisig, per-call cap)."
                ),
                actuarial=(
                    "Target reserve R comes from `simulate_fund`&rsquo;s p95 "
                    "shortfall. Release reverts unless "
                    "`stressLevel &ge; releaseThreshold` and "
                    "`amount &le; perCallCapBps &middot; reserve`."
                ),
            )
            bs_seed = st.number_input(
                "Seed reserve (ETH)", value=5.0, min_value=0.01, step=1.0,
                key="bridge_bs_seed",
            )
            bs_release = st.number_input(
                "Release (ETH)", value=1.0, min_value=0.01, step=0.5,
                key="bridge_bs_release",
            )
            with st.expander("Raw bridged payload &mdash; BackstopVault.deposit + release"):
                st.json(encode_backstop_deposit(bs_seed).as_dict())
                st.json(encode_backstop_release(bs_release).as_dict())

        if st.button("Record bridge hand-off to audit chain"):
            event_log.append(
                "bridge_handoff",
                calls=len(calls), cohorts=len(cv),
                proposal=prop_name, stress_level=stress_level,
            )
            st.success("Hand-off hashed into audit chain.")
