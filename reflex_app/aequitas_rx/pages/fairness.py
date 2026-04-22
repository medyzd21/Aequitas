"""Fairness & Governance page.

Three sections, all wired to the live engine:

  1. Point-in-time fairness KPIs + MWR-by-cohort bar chart with the
     parity reference line.
  2. Governance sandbox — propose per-cohort multipliers, evaluate
     against the fairness corridor, show PASS/FAIL and a before/after
     MWR table.
  3. Stochastic fairness stress — Monte-Carlo cohort shocks with
     β-loaded generational risk, producing the full result set the
     Streamlit build used to show (mean / p95 Gini, mean / p05 intergen
     index, corridor pass rate, youngest-poor rate, β chart,
     worst-affected-cohort frequencies, Gini histogram).
"""
from __future__ import annotations

import reflex as rx

from ..components import pill, shell, simple_table, sidebar_controls
from ..state import AppState
from ..theme import CARD_STYLE, PALETTE


# --------------------------------------------------------------------------- point-in-time
def _fairness_kpis() -> rx.Component:
    return rx.hstack(
        rx.box(
            rx.text("MWR min → max",
                    style={"color": PALETTE["muted"], "font_size": "11px"}),
            rx.text(AppState.mwr_range_fmt,
                    style={"color": PALETTE["text"],
                           "font_size": "18px", "font_weight": "600"}),
            style={**CARD_STYLE, "flex": "1"},
        ),
        rx.box(
            rx.text("MWR std dev",
                    style={"color": PALETTE["muted"], "font_size": "11px"}),
            rx.text(AppState.mwr_std_fmt,
                    style={"color": PALETTE["text"],
                           "font_size": "18px", "font_weight": "600"}),
            style={**CARD_STYLE, "flex": "1"},
        ),
        rx.box(
            rx.text("Gini (MWR)",
                    style={"color": PALETTE["muted"], "font_size": "11px"}),
            rx.text(AppState.gini_fmt,
                    style={"color": PALETTE["text"],
                           "font_size": "18px", "font_weight": "600"}),
            style={**CARD_STYLE, "flex": "1"},
        ),
        rx.box(
            rx.text("Intergen index",
                    style={"color": PALETTE["muted"], "font_size": "11px"}),
            rx.text(AppState.intergen_fmt,
                    style={"color": PALETTE["text"],
                           "font_size": "18px", "font_weight": "600"}),
            style={**CARD_STYLE, "flex": "1"},
        ),
        spacing="3",
        width="100%",
    )


def _mwr_chart() -> rx.Component:
    return rx.box(
        rx.text("MWR by cohort (parity = 1.00)",
                style={"color": PALETTE["text"], "font_weight": "600",
                       "font_size": "14px", "margin_bottom": "4px"}),
        rx.text(
            "Money's-Worth Ratio per cohort. Bars on or above the dashed "
            "parity line are earning back their actuarial entitlement; "
            "bars below it are subsidising other cohorts.",
            style={"color": PALETTE["muted"], "font_size": "11px",
                   "margin_bottom": "8px"},
        ),
        rx.cond(
            AppState.cohorts_count >= 2,
            rx.recharts.bar_chart(
                rx.recharts.bar(data_key="mwr", fill=PALETTE["accent"]),
                rx.recharts.x_axis(data_key="cohort",
                                   stroke=PALETTE["muted"]),
                rx.recharts.y_axis(stroke=PALETTE["muted"]),
                rx.recharts.cartesian_grid(stroke=PALETTE["edge"]),
                rx.recharts.reference_line(
                    y=1, stroke=PALETTE["muted"],
                    stroke_dasharray="4 4",
                ),
                rx.recharts.graphing_tooltip(),
                data=AppState.cohort_mwr_rows,
                width="100%",
                height=260,
            ),
            rx.text("Need ≥ 2 cohorts.", style={"color": PALETTE["muted"]}),
        ),
        style=CARD_STYLE,
    )


# --------------------------------------------------------------------------- governance sandbox
def _sandbox() -> rx.Component:
    return rx.box(
        rx.hstack(
            rx.text("Governance sandbox",
                    style={"color": PALETTE["text"], "font_weight": "600",
                           "font_size": "14px"}),
            rx.spacer(),
            pill("FairnessGate.submitAndEvaluate", "muted"),
            align="center",
            width="100%",
            margin_bottom="4px",
        ),
        rx.text(
            "Propose a benefit multiplier per cohort (1.00 = no change). "
            "Aequitas evaluates the proposal against the fairness corridor "
            "δ and only a pass reaches the on-chain gate.",
            style={"color": PALETTE["muted"], "font_size": "11px",
                   "margin_bottom": "10px"},
        ),
        rx.cond(
            AppState.cohorts_count >= 2,
            rx.vstack(
                rx.hstack(
                    rx.foreach(
                        AppState.cohort_mwr_rows,
                        lambda row: rx.vstack(
                            rx.text(row["cohort"].to_string(),
                                    style={"color": PALETTE["muted"],
                                           "font_size": "11px"}),
                            rx.input(
                                default_value="1.00",
                                on_change=lambda v: AppState.set_multiplier(
                                    row["cohort"].to_string(), v,
                                ),
                                type="number",
                                step="0.01",
                                size="1",
                                width="80px",
                            ),
                            spacing="1",
                            align="center",
                        ),
                    ),
                    spacing="2",
                    wrap="wrap",
                ),
                rx.hstack(
                    rx.text("Corridor δ (%)",
                            style={"color": PALETTE["muted"],
                                   "font_size": "11px"}),
                    rx.input(
                        value=AppState.corridor_delta_pct.to_string(),
                        on_change=AppState.set_corridor_delta,
                        type="number",
                        step=1,
                        size="1",
                        width="80px",
                    ),
                    rx.button(
                        "Evaluate proposal",
                        on_click=AppState.evaluate_sandbox_proposal,
                        color_scheme="cyan",
                        size="2",
                    ),
                    spacing="3",
                    align="center",
                ),
                rx.cond(
                    AppState.sandbox_ran,
                    rx.vstack(
                        rx.hstack(
                            rx.cond(
                                AppState.sandbox_is_pass,
                                pill("CORRIDOR PASSES", "good"),
                                pill("CORRIDOR FAILS", "bad"),
                            ),
                            rx.text(AppState.sandbox_verdict,
                                    style={"color": PALETTE["text"],
                                           "font_size": "12px"}),
                            spacing="2",
                            align="center",
                        ),
                        simple_table(
                            [("cohort", "Cohort"),
                             ("mwr_before", "MWR before"),
                             ("mwr_after", "MWR after")],
                            AppState.sandbox_comparison_rows,
                        ),
                        spacing="2",
                        align="start",
                        width="100%",
                    ),
                    rx.text(""),
                ),
                spacing="3",
                width="100%",
                align="start",
            ),
            rx.text("Load demo data and register ≥ 2 cohorts.",
                    style={"color": PALETTE["muted"]}),
        ),
        style=CARD_STYLE,
    )


# --------------------------------------------------------------------------- stochastic stress
def _stress_input(label: str, value_var, handler, step="1",
                  width="80px") -> rx.Component:
    return rx.vstack(
        rx.text(label,
                style={"color": PALETTE["muted"], "font_size": "11px"}),
        rx.input(
            value=value_var.to_string(),
            on_change=handler,
            type="number",
            step=step,
            size="1",
            width=width,
        ),
        spacing="1",
        align="start",
    )


def _stress_knobs() -> rx.Component:
    return rx.hstack(
        _stress_input("Scenarios",
                      AppState.stress_scenarios,
                      AppState.change_stress_scenarios),
        _stress_input("Macro σ_F (%)",
                      AppState.stress_factor_sigma_pct,
                      AppState.change_stress_factor_sigma),
        _stress_input("Idio σ_ε (%)",
                      AppState.stress_idiosyncratic_sigma_pct,
                      AppState.change_stress_idio_sigma),
        _stress_input("Gen. slope |β_max| (%)",
                      AppState.stress_generational_slope_pct,
                      AppState.change_stress_slope),
        _stress_input("Corridor δ (%)",
                      AppState.stress_corridor_delta_pct,
                      AppState.change_stress_corridor),
        _stress_input("Youngest-poor MWR (%)",
                      AppState.stress_youngest_poor_pct,
                      AppState.change_stress_poor),
        _stress_input("Seed",
                      AppState.stress_seed,
                      AppState.change_stress_seed),
        rx.button(
            "Run stress",
            on_click=AppState.run_stress,
            color_scheme="cyan",
            size="2",
            margin_top="16px",
        ),
        spacing="3",
        width="100%",
        align="start",
        wrap="wrap",
    )


def _stress_kpi(label: str, value_var, pill_var=None) -> rx.Component:
    return rx.box(
        rx.text(label,
                style={"color": PALETTE["muted"], "font_size": "10px",
                       "letter_spacing": "0.08em",
                       "text_transform": "uppercase"}),
        rx.text(value_var,
                style={"color": PALETTE["text"], "font_size": "18px",
                       "font_weight": "600", "margin_top": "2px"}),
        rx.cond(
            pill_var is not None,
            rx.match(
                pill_var if pill_var is not None else "muted",
                ("good",  pill("STRONG", "good")),
                ("warn",  pill("WATCH", "warn")),
                ("bad",   pill("STRESS", "bad")),
                pill("NO DATA", "muted"),
            ),
            rx.text(""),
        ),
        style={**CARD_STYLE, "flex": "1", "min_width": "140px"},
    )


def _stress_kpis() -> rx.Component:
    return rx.hstack(
        _stress_kpi("Mean Gini",    AppState.stress_mean_gini_fmt),
        _stress_kpi("p95 Gini",     AppState.stress_p95_gini_fmt),
        _stress_kpi("Mean intergen index", AppState.stress_mean_index_fmt),
        _stress_kpi("p05 intergen index",  AppState.stress_p05_index_fmt),
        _stress_kpi("Corridor pass rate",  AppState.stress_pass_rate_fmt,
                    AppState.stress_pass_pill),
        _stress_kpi("P(MWR < threshold on youngest)",
                    AppState.stress_youngest_rate_fmt,
                    AppState.stress_youngest_pill),
        spacing="3",
        width="100%",
        wrap="wrap",
    )


def _stress_charts() -> rx.Component:
    return rx.hstack(
        rx.box(
            rx.text("Cohort β loadings",
                    style={"color": PALETTE["text"], "font_weight": "600",
                           "font_size": "13px", "margin_bottom": "4px"}),
            rx.text(
                "Systemic sensitivity per cohort in the one-factor shock "
                "m_c(s) = 1 + β_c·F(s) + ε_c(s). Positive β means the "
                "cohort carries more systemic risk than the pool average.",
                style={"color": PALETTE["muted"], "font_size": "11px",
                       "margin_bottom": "6px"},
            ),
            rx.recharts.bar_chart(
                rx.recharts.bar(data_key="beta", fill=PALETTE["accent"]),
                rx.recharts.x_axis(data_key="cohort",
                                   stroke=PALETTE["muted"]),
                rx.recharts.y_axis(stroke=PALETTE["muted"]),
                rx.recharts.cartesian_grid(stroke=PALETTE["edge"]),
                rx.recharts.reference_line(
                    y=0, stroke=PALETTE["muted"],
                    stroke_dasharray="4 4",
                ),
                rx.recharts.graphing_tooltip(),
                data=AppState.stress_beta_rows,
                width="100%",
                height=220,
            ),
            style={**CARD_STYLE, "flex": "1"},
        ),
        rx.box(
            rx.text("Worst-affected-cohort frequency",
                    style={"color": PALETTE["text"], "font_weight": "600",
                           "font_size": "13px", "margin_bottom": "4px"}),
            rx.text(
                "Over the full scenario set, how often each cohort ended "
                "up with the single lowest MWR. A tall bar on the young "
                "side signals the scheme systematically loses the youngest "
                "generation under stress.",
                style={"color": PALETTE["muted"], "font_size": "11px",
                       "margin_bottom": "6px"},
            ),
            rx.recharts.bar_chart(
                rx.recharts.bar(data_key="freq", fill="#f472b6"),
                rx.recharts.x_axis(data_key="cohort",
                                   stroke=PALETTE["muted"]),
                rx.recharts.y_axis(stroke=PALETTE["muted"]),
                rx.recharts.cartesian_grid(stroke=PALETTE["edge"]),
                rx.recharts.graphing_tooltip(),
                data=AppState.stress_worst_rows,
                width="100%",
                height=220,
            ),
            style={**CARD_STYLE, "flex": "1"},
        ),
        spacing="3",
        width="100%",
        align="stretch",
    )


def _stress_histogram() -> rx.Component:
    return rx.box(
        rx.text("Scenario distribution — Gini of MWR",
                style={"color": PALETTE["text"], "font_weight": "600",
                       "font_size": "13px", "margin_bottom": "4px"}),
        rx.text(
            "Density of per-scenario Gini outcomes. A tight left-leaning "
            "distribution means the scheme is fair across almost all "
            "plausible futures; a heavy right tail flags scenarios where "
            "intergenerational dispersion blows out.",
            style={"color": PALETTE["muted"], "font_size": "11px",
                   "margin_bottom": "6px"},
        ),
        rx.recharts.bar_chart(
            rx.recharts.bar(data_key="count", fill=PALETTE["accent"]),
            rx.recharts.x_axis(data_key="bin",
                               stroke=PALETTE["muted"]),
            rx.recharts.y_axis(stroke=PALETTE["muted"]),
            rx.recharts.cartesian_grid(stroke=PALETTE["edge"]),
            rx.recharts.graphing_tooltip(),
            data=AppState.stress_gini_hist,
            width="100%",
            height=220,
        ),
        style=CARD_STYLE,
    )


def _stress_section() -> rx.Component:
    return rx.box(
        rx.hstack(
            rx.text("Stochastic fairness stress",
                    style={"color": PALETTE["text"], "font_weight": "600",
                           "font_size": "14px"}),
            rx.spacer(),
            pill("StressOracle.updateStressLevel", "muted"),
            align="center",
            width="100%",
            margin_bottom="4px",
        ),
        rx.text(
            "Monte-Carlo the fairness corridor. Each scenario applies a "
            "one-factor cohort shock m_c(s) = 1 + β_c·F(s) + ε_c(s) and "
            "recomputes the Gini / intergen index / corridor pass. The "
            "result is what StressOracle would publish on-chain to drive "
            "BackstopVault.release decisions.",
            style={"color": PALETTE["muted"], "font_size": "11px",
                   "margin_bottom": "10px"},
        ),
        _stress_knobs(),
        rx.box(style={"height": "10px"}),
        rx.cond(
            AppState.stress_ran,
            rx.vstack(
                _stress_kpis(),
                _stress_charts(),
                _stress_histogram(),
                spacing="3",
                width="100%",
                align="stretch",
            ),
            rx.box(
                rx.text(
                    "Set the knobs and click Run stress to Monte-Carlo "
                    "the corridor. The seed is kept explicit so every run "
                    "is reproducible.",
                    style={"color": PALETTE["muted"], "font_size": "11px"},
                ),
                style={"padding": "6px 0"},
            ),
        ),
        style={**CARD_STYLE,
               "border_left": f"3px solid {PALETTE['accent']}"},
    )


# --------------------------------------------------------------------------- page
def fairness_page() -> rx.Component:
    return shell(
        "Fairness & governance",
        "Is every generation treated fairly? We measure deviation from "
        "parity (MWR = 1.00), dispersion across cohorts (Gini), and "
        "whether proposals clear the fairness corridor before they "
        "execute. The stochastic stress panel below carries the same "
        "test across thousands of plausible futures.",
        rx.hstack(
            sidebar_controls(),
            rx.vstack(
                _fairness_kpis(),
                _mwr_chart(),
                _sandbox(),
                _stress_section(),
                spacing="3",
                width="100%",
                align="stretch",
            ),
            spacing="3",
            width="100%",
            align="start",
        ),
    )
