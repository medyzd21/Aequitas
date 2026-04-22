"""Digital Twin page — population × fund × fairness through time.

This page takes the repo's population generator, the actuarial engine and
the fairness stress module and wraps them in the `run_system_simulation`
driver. The user picks a scenario + horizon, clicks Run, and every panel
below fills with a synchronised time series.

Panels rendered (in order):

  1. Scenario selector + run button + summary KPIs.
  2. Population evolution — active / retired / deceased over time.
  3. Fund evolution — NAV, contributions, benefits, backstop reserve.
  4. Fairness evolution — Gini, intergen index, scheme MWR, funded ratio.
  5. Cohort MWR trajectories — one line per cohort.
  6. Representative stories — lifecycle archetypes (young / mid / near /
     retiree) and how their personal fund changes through time.
  7. Event timeline — every SimEvent with its Solidity contract tag.
  8. Hybrid story footer — Python = truth, Solidity = execution.
"""
from __future__ import annotations

import reflex as rx

from ..components import pill, shell
from ..state import AppState
from ..theme import CARD_STYLE, PALETTE, SERIES


# --------------------------------------------------------------------------- small helpers
def _panel(title: str, *children, subtitle: str = "") -> rx.Component:
    return rx.box(
        rx.text(title,
                style={"color": PALETTE["text"], "font_weight": "600",
                       "font_size": "14px", "margin_bottom": "2px"}),
        rx.cond(
            subtitle != "",
            rx.text(subtitle,
                    style={"color": PALETTE["muted"], "font_size": "11px",
                           "margin_bottom": "8px"}),
            rx.fragment(),
        ),
        *children,
        style={**CARD_STYLE, "margin_bottom": "12px"},
    )


def _twin_kpi(label, value, sub=None) -> rx.Component:
    return rx.box(
        rx.text(label,
                style={"color": PALETTE["muted"], "font_size": "10px",
                       "letter_spacing": "0.08em",
                       "text_transform": "uppercase",
                       "margin_bottom": "2px"}),
        rx.text(value,
                style={"color": PALETTE["text"], "font_size": "18px",
                       "font_weight": "600", "line_height": "1.2"}),
        sub if sub is not None else rx.fragment(),
        style={**CARD_STYLE, "flex": "1 1 0", "min_width": "150px"},
    )


# --------------------------------------------------------------------------- controls
def _controls_block() -> rx.Component:
    return rx.box(
        rx.heading("Scenario", size="3", style={"color": PALETTE["text"]}),
        rx.text(
            "Choose a scenario and a horizon. The simulator runs the actuarial "
            "engine year-by-year, emits a SimEvent for every step and maps "
            "each one to its Solidity contract.",
            style={"color": PALETTE["muted"], "font_size": "11px",
                   "margin_top": "4px", "margin_bottom": "10px"},
        ),
        rx.select(
            [
                "stable", "inflation_shock", "market_crash",
                "aging_society", "unfair_reform", "young_stress",
            ],
            value=AppState.twin_scenario,
            on_change=AppState.change_twin_scenario,
            size="2",
            width="100%",
        ),
        rx.text(AppState.twin_scenario_description,
                style={"color": PALETTE["muted"], "font_size": "11px",
                       "font_style": "italic",
                       "margin_top": "6px", "margin_bottom": "8px"}),
        rx.text("Horizon (years)",
                style={"color": PALETTE["muted"], "font_size": "11px",
                       "margin_top": "6px"}),
        rx.input(
            value=AppState.twin_years.to_string(),
            on_change=AppState.change_twin_years,
            type="number",
            size="1",
        ),
        rx.text("Population size",
                style={"color": PALETTE["muted"], "font_size": "11px",
                       "margin_top": "6px"}),
        rx.input(
            value=AppState.twin_n_members.to_string(),
            on_change=AppState.change_twin_n_members,
            type="number",
            size="1",
        ),
        rx.text("Random seed",
                style={"color": PALETTE["muted"], "font_size": "11px",
                       "margin_top": "6px"}),
        rx.input(
            value=AppState.twin_seed.to_string(),
            on_change=AppState.change_twin_seed,
            type="number",
            size="1",
        ),
        rx.button(
            "Run digital twin",
            on_click=AppState.run_twin_simulation,
            color_scheme="cyan",
            size="2",
            width="100%",
            margin_top="12px",
        ),
        rx.text(
            "Tip: 1000 members × 30 years runs in ~1 second. "
            "Scale up to 10 000 for a stress-scale run.",
            style={"color": PALETTE["muted"], "font_size": "10px",
                   "margin_top": "8px"},
        ),
        style={**CARD_STYLE, "width": "260px", "flex_shrink": "0"},
    )


# --------------------------------------------------------------------------- summary KPIs
def _summary_kpis() -> rx.Component:
    return rx.hstack(
        _twin_kpi("Final members", AppState.twin_final_members,
                  rx.text(f"{AppState.twin_final_retirees} retired · "
                          f"{AppState.twin_final_deceased} deceased",
                          style={"color": PALETTE["muted"],
                                 "font_size": "10px"})),
        _twin_kpi("Peak fund NAV", AppState.twin_peak_nav_fmt,
                  rx.text(AppState.twin_peak_nav_year_fmt,
                          style={"color": PALETTE["muted"],
                                 "font_size": "10px"})),
        _twin_kpi("Final funded ratio", AppState.twin_final_funded_ratio_fmt,
                  rx.match(
                      AppState.twin_funded_pill,
                      ("good", pill("HEALTHY", "good")),
                      ("warn", pill("WATCH", "warn")),
                      ("bad",  pill("STRESS", "bad")),
                      pill("NO RUN", "muted"),
                  )),
        _twin_kpi("Avg Gini (MWR)", AppState.twin_avg_gini_fmt,
                  rx.match(
                      AppState.twin_gini_pill,
                      ("good", pill("HEALTHY", "good")),
                      ("warn", pill("WATCH", "warn")),
                      ("bad",  pill("STRESS", "bad")),
                      pill("NO RUN", "muted"),
                  )),
        _twin_kpi("Total contributions", AppState.twin_total_contrib_fmt),
        _twin_kpi("Total benefits paid", AppState.twin_total_benefit_fmt),
        _twin_kpi("Backstop reserve", AppState.twin_final_reserve_fmt),
        _twin_kpi("Events emitted", AppState.twin_event_count,
                  rx.text(f"{AppState.twin_crashes_count} crashes · "
                          f"{AppState.twin_proposals_count} proposals",
                          style={"color": PALETTE["muted"],
                                 "font_size": "10px"})),
        spacing="2",
        width="100%",
        wrap="wrap",
        align="stretch",
    )


# --------------------------------------------------------------------------- charts
def _population_chart() -> rx.Component:
    return _panel(
        "Population evolution",
        rx.recharts.area_chart(
            rx.recharts.area(data_key="active",    stack_id="pop",
                              fill=SERIES[0], stroke=SERIES[0]),
            rx.recharts.area(data_key="retired",   stack_id="pop",
                              fill=SERIES[2], stroke=SERIES[2]),
            rx.recharts.area(data_key="deceased",  stack_id="pop",
                              fill=SERIES[3], stroke=SERIES[3]),
            rx.recharts.x_axis(data_key="year", stroke=PALETTE["muted"]),
            rx.recharts.y_axis(stroke=PALETTE["muted"]),
            rx.recharts.cartesian_grid(stroke=PALETTE["edge"]),
            rx.recharts.legend(),
            rx.recharts.graphing_tooltip(),
            data=AppState.twin_annual_rows,
            width="100%",
            height=260,
        ),
        subtitle="Stacked: active (cyan) + retired (emerald) + deceased (amber).",
    )


def _fund_chart() -> rx.Component:
    return _panel(
        "Fund evolution",
        rx.recharts.line_chart(
            rx.recharts.line(data_key="fund_nav",
                              stroke=PALETTE["accent"], stroke_width=2,
                              dot=False),
            rx.recharts.line(data_key="total_contrib",
                              stroke=PALETTE["good"], stroke_width=2,
                              dot=False),
            rx.recharts.line(data_key="total_benefit",
                              stroke=PALETTE["warn"], stroke_width=2,
                              dot=False),
            rx.recharts.line(data_key="reserve",
                              stroke=SERIES[1], stroke_width=2,
                              dot=False, stroke_dasharray="4 4"),
            rx.recharts.x_axis(data_key="year", stroke=PALETTE["muted"]),
            rx.recharts.y_axis(stroke=PALETTE["muted"]),
            rx.recharts.cartesian_grid(stroke=PALETTE["edge"]),
            rx.recharts.legend(),
            rx.recharts.graphing_tooltip(),
            data=AppState.twin_annual_rows,
            width="100%",
            height=260,
        ),
        subtitle=(
            "Fund NAV (cyan), yearly contributions (emerald), "
            "yearly benefits paid (amber), BackstopVault reserve (violet dashed)."
        ),
    )


def _fairness_chart() -> rx.Component:
    return _panel(
        "Fairness evolution",
        rx.recharts.line_chart(
            rx.recharts.line(data_key="gini",
                              stroke=SERIES[4], stroke_width=2, dot=False),
            rx.recharts.line(data_key="intergen_index",
                              stroke=SERIES[0], stroke_width=2, dot=False),
            rx.recharts.line(data_key="mwr_scheme",
                              stroke=SERIES[2], stroke_width=2, dot=False),
            rx.recharts.line(data_key="funded_ratio",
                              stroke=SERIES[3], stroke_width=2, dot=False),
            rx.recharts.x_axis(data_key="year", stroke=PALETTE["muted"]),
            rx.recharts.y_axis(stroke=PALETTE["muted"]),
            rx.recharts.cartesian_grid(stroke=PALETTE["edge"]),
            rx.recharts.legend(),
            rx.recharts.graphing_tooltip(),
            data=AppState.twin_annual_rows,
            width="100%",
            height=260,
        ),
        subtitle=(
            "Gini (pink), Intergen index (cyan), Scheme MWR (emerald), "
            "Funded ratio (amber). Parity line = 1.0."
        ),
    )


def _cohort_trajectories_chart() -> rx.Component:
    return _panel(
        "Cohort MWR trajectories",
        rx.cond(
            AppState.twin_cohort_keys.length() > 0,
            rx.recharts.line_chart(
                rx.foreach(
                    AppState.twin_cohort_keys,
                    lambda key, i: rx.recharts.line(
                        data_key=key,
                        stroke=rx.color_mode_cond(
                            light=SERIES[0],
                            dark=SERIES[0],
                        ),
                        stroke_width=1.5,
                        dot=False,
                    ),
                ),
                rx.recharts.x_axis(data_key="year", stroke=PALETTE["muted"]),
                rx.recharts.y_axis(stroke=PALETTE["muted"]),
                rx.recharts.cartesian_grid(stroke=PALETTE["edge"]),
                rx.recharts.legend(),
                rx.recharts.graphing_tooltip(),
                data=AppState.twin_cohort_pivot_rows,
                width="100%",
                height=260,
            ),
            rx.text("Run the twin to see cohort MWR trajectories.",
                    style={"color": PALETTE["muted"]}),
        ),
        subtitle=(
            "Each line is one birth cohort's Money Worth Ratio "
            "through time. Parity = 1.00 — a line above 1 means that "
            "cohort has been promised more than it has paid in, below "
            "means less."
        ),
    )


# --------------------------------------------------------------------------- representative stories
def _rep_chart(title: str, rows_var) -> rx.Component:
    return rx.box(
        rx.text(title,
                style={"color": PALETTE["text"], "font_weight": "600",
                       "font_size": "12px", "margin_bottom": "4px"}),
        rx.cond(
            rows_var.length() > 0,
            rx.recharts.line_chart(
                rx.recharts.line(data_key="fund",
                                  stroke=PALETTE["accent"], stroke_width=2,
                                  dot=False),
                rx.recharts.line(data_key="benefit",
                                  stroke=PALETTE["good"], stroke_width=2,
                                  dot=False),
                rx.recharts.x_axis(data_key="year",
                                    stroke=PALETTE["muted"]),
                rx.recharts.y_axis(stroke=PALETTE["muted"]),
                rx.recharts.cartesian_grid(stroke=PALETTE["edge"]),
                rx.recharts.graphing_tooltip(),
                data=rows_var,
                width="100%",
                height=160,
            ),
            rx.text("—", style={"color": PALETTE["muted"]}),
        ),
        style={**CARD_STYLE, "flex": "1 1 48%", "min_width": "280px"},
    )


def _representative_stories() -> rx.Component:
    return _panel(
        "Representative stories",
        rx.hstack(
            _rep_chart("Young (joined recently)",
                       AppState.twin_rep_young_rows),
            _rep_chart("Mid-career",
                       AppState.twin_rep_mid_rows),
            spacing="3",
            width="100%",
            wrap="wrap",
            align="stretch",
        ),
        rx.hstack(
            _rep_chart("Near retirement",
                       AppState.twin_rep_near_rows),
            _rep_chart("Retiree",
                       AppState.twin_rep_retiree_rows),
            spacing="3",
            width="100%",
            wrap="wrap",
            align="stretch",
            margin_top="8px",
        ),
        subtitle=(
            "Four lifecycle archetypes picked at sim start. Cyan line = "
            "personal fund balance; emerald line = locked annual benefit "
            "once the member has retired."
        ),
    )


# --------------------------------------------------------------------------- event timeline
def _severity_pill(severity) -> rx.Component:
    return rx.match(
        severity,
        ("good", pill("GOOD", "good")),
        ("warn", pill("WARN", "warn")),
        ("bad",  pill("BAD",  "bad")),
        pill("—", "muted"),
    )


def _event_timeline() -> rx.Component:
    return _panel(
        "Event timeline",
        rx.cond(
            AppState.twin_event_rows.length() > 0,
            rx.box(
                rx.foreach(
                    AppState.twin_event_rows,
                    lambda e: rx.hstack(
                        rx.text(e["year"], style={
                            "color": PALETTE["muted"],
                            "font_family": "monospace",
                            "font_size": "11px",
                            "width": "50px", "flex_shrink": "0",
                        }),
                        _severity_pill(e["severity"]),
                        rx.text(e["message"], style={
                            "color": PALETTE["text"],
                            "font_size": "12px",
                            "flex_grow": "1",
                        }),
                        pill(e["contract"], "muted"),
                        spacing="2",
                        align="center",
                        width="100%",
                        padding="4px 0",
                        border_bottom=f"1px solid {PALETTE['edge']}",
                    ),
                ),
                style={"max_height": "360px", "overflow_y": "auto"},
            ),
            rx.text("Run the twin to populate the event timeline.",
                    style={"color": PALETTE["muted"]}),
        ),
        subtitle=(
            "Each row is one SimEvent. Severity pill = colour code. Right "
            "pill = the Solidity contract that would execute the event "
            "on-chain. This mapping is the hybrid story in miniature."
        ),
    )


def _event_summary_grid() -> rx.Component:
    return rx.cond(
        AppState.twin_event_summary_rows.length() > 0,
        rx.box(
            rx.text("Event kind counts",
                    style={"color": PALETTE["muted"], "font_size": "11px",
                           "margin_bottom": "4px"}),
            rx.hstack(
                rx.foreach(
                    AppState.twin_event_summary_rows,
                    lambda r: rx.box(
                        rx.text(r["kind"], style={
                            "color": PALETTE["text"],
                            "font_size": "11px",
                            "font_weight": "500",
                        }),
                        rx.text(r["count"], style={
                            "color": PALETTE["accent"],
                            "font_size": "14px",
                            "font_weight": "600",
                        }),
                        style={
                            "background": PALETTE["panel"],
                            "border": f"1px solid {PALETTE['edge']}",
                            "border_radius": "6px",
                            "padding": "4px 10px",
                        },
                    ),
                ),
                spacing="2",
                wrap="wrap",
            ),
            margin_top="6px",
        ),
        rx.fragment(),
    )


# --------------------------------------------------------------------------- hybrid footer
def _hybrid_footer() -> rx.Component:
    return rx.box(
        rx.heading("Hybrid architecture",
                   size="4",
                   style={"color": PALETTE["text"], "margin_bottom": "6px"}),
        rx.text(
            "Every SimEvent above carries the name of the Solidity contract "
            "that would execute the equivalent action on-chain. That is the "
            "Aequitas hybrid principle made concrete:",
            style={"color": PALETTE["muted"], "font_size": "12px",
                   "margin_bottom": "8px"},
        ),
        rx.hstack(
            rx.box(
                pill("PYTHON", "good"),
                rx.text(" = actuarial truth",
                        style={"color": PALETTE["text"],
                               "font_weight": "600", "margin_top": "6px"}),
                rx.text(
                    "The engine in this page — GompertzMakeham, EPV, "
                    "cohort MWR, Gini, the fairness corridor and the "
                    "stochastic stress — is the source of truth. It runs "
                    "the digital twin, decides whether a proposal passes, "
                    "and shapes the reserve policy.",
                    style={"color": PALETTE["muted"], "font_size": "11px",
                           "margin_top": "4px", "line_height": "1.5"},
                ),
                style={**CARD_STYLE, "flex": "1 1 0"},
            ),
            rx.box(
                pill("SOLIDITY", "warn"),
                rx.text(" = execution & audit",
                        style={"color": PALETTE["text"],
                               "font_weight": "600", "margin_top": "6px"}),
                rx.text(
                    "Eight contracts (CohortLedger, FairnessGate, "
                    "LongevaPool, MortalityOracle, VestaRouter, "
                    "BenefitStreamer, StressOracle, BackstopVault) execute "
                    "the decisions on-chain. The engine's chain_bridge "
                    "module emits a ChainCall for every SimEvent so the "
                    "timeline is always replayable.",
                    style={"color": PALETTE["muted"], "font_size": "11px",
                           "margin_top": "4px", "line_height": "1.5"},
                ),
                style={**CARD_STYLE, "flex": "1 1 0"},
            ),
            spacing="3",
            width="100%",
            align="stretch",
        ),
        style={**CARD_STYLE, "margin_top": "14px"},
    )


# --------------------------------------------------------------------------- page
def twin_page() -> rx.Component:
    return shell(
        "Digital Twin",
        "A time-evolving synthetic pension scheme. One click runs the full "
        "actuarial engine year-by-year — population turnover, contributions, "
        "returns, retirements, mortality, fairness stress, governance — and "
        "every event is mapped to the Solidity contract that would execute "
        "it on-chain.",
        rx.hstack(
            _controls_block(),
            rx.vstack(
                _summary_kpis(),
                _event_summary_grid(),
                rx.hstack(
                    _population_chart(),
                    _fund_chart(),
                    spacing="3",
                    width="100%",
                    align="stretch",
                ),
                rx.hstack(
                    _fairness_chart(),
                    _cohort_trajectories_chart(),
                    spacing="3",
                    width="100%",
                    align="stretch",
                ),
                _representative_stories(),
                _event_timeline(),
                _hybrid_footer(),
                spacing="3",
                width="100%",
                align="stretch",
            ),
            spacing="3",
            width="100%",
            align="start",
        ),
    )
