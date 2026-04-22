"""Members & Cohorts page.

Roster + per-member actuarial valuation + a drill-down with a proper
selector. Representative-profile chips let the professor demo the
member lifecycle in one click (young contributor → mid-career →
near-retiree → retiree).
"""
from __future__ import annotations

import reflex as rx

from ..components import shell, simple_table, sidebar_controls
from ..state import AppState
from ..theme import CARD_STYLE, PALETTE


# --------------------------------------------------------------------------- roster + composition
def _roster_card() -> rx.Component:
    return rx.box(
        rx.text("Member roster",
                style={"color": PALETTE["text"], "font_weight": "600",
                       "font_size": "14px", "margin_bottom": "8px"}),
        rx.cond(
            AppState.loaded,
            simple_table(
                [
                    ("wallet",             "Wallet"),
                    ("cohort",             "Cohort"),
                    ("age",                "Age"),
                    ("salary",             "Salary"),
                    ("contribution_rate",  "Contrib rate"),
                    ("retirement_age",     "Retire age"),
                    ("total_contributions", "Contrib total"),
                    ("piu_balance",        "PIU balance"),
                ],
                AppState.member_rows,
            ),
            rx.text("Load demo data to populate the register.",
                    style={"color": PALETTE["muted"]}),
        ),
        style=CARD_STYLE,
    )


def _cohort_composition() -> rx.Component:
    return rx.box(
        rx.text("Cohort composition",
                style={"color": PALETTE["text"], "font_weight": "600",
                       "font_size": "14px", "margin_bottom": "8px"}),
        rx.cond(
            AppState.cohort_contrib_rows.length() > 0,
            rx.recharts.bar_chart(
                rx.recharts.bar(data_key="total_contributions",
                                fill=PALETTE["accent"]),
                rx.recharts.x_axis(data_key="cohort",
                                   stroke=PALETTE["muted"]),
                rx.recharts.y_axis(stroke=PALETTE["muted"]),
                rx.recharts.cartesian_grid(stroke=PALETTE["edge"]),
                rx.recharts.graphing_tooltip(),
                data=AppState.cohort_contrib_rows,
                width="100%",
                height=240,
            ),
            rx.text("—", style={"color": PALETTE["muted"]}),
        ),
        style=CARD_STYLE,
    )


# --------------------------------------------------------------------------- valuation
def _valuation_card() -> rx.Component:
    return rx.box(
        rx.text("Per-member actuarial valuation",
                style={"color": PALETTE["text"], "font_weight": "600",
                       "font_size": "14px", "margin_bottom": "4px"}),
        rx.text(
            "EPV = Σ vᵗ · ₜpₓ · CFₜ with a Gompertz–Makeham life table. "
            "Money's Worth Ratio = EPV(benefits) / EPV(contributions).",
            style={"color": PALETTE["muted"], "font_size": "11px",
                   "margin_bottom": "8px"},
        ),
        rx.cond(
            AppState.loaded,
            simple_table(
                [
                    ("wallet",                   "Wallet"),
                    ("epv_contributions",        "EPV contrib"),
                    ("epv_benefits",             "EPV benefit"),
                    ("money_worth_ratio",        "MWR"),
                    ("projected_annual_benefit", "Projected B"),
                    ("replacement_ratio",        "Replacement"),
                ],
                AppState.valuation_rows,
            ),
            rx.text("—", style={"color": PALETTE["muted"]}),
        ),
        style=CARD_STYLE,
    )


# --------------------------------------------------------------------------- drill-down
_PROFILES = [
    ("young", "Young contributor",
     "Early in accumulation. Maximum exposure to systemic β shocks."),
    ("mid", "Mid-career",
     "Peak salary growth. Dominant driver of EPV(contributions)."),
    ("near", "Near-retiree",
     "About to flip to decumulation. Most sensitive to terminal assumptions."),
    ("retiree", "Retiree-track",
     "Past retirement age under current assumptions — LongevaPool-facing."),
]


def _profile_chip(key: str, label: str, desc: str) -> rx.Component:
    selected = AppState.active_profile == key
    return rx.box(
        rx.vstack(
            rx.text(label,
                    style={"color": PALETTE["text"], "font_weight": "600",
                           "font_size": "12px"}),
            rx.text(desc,
                    style={"color": PALETTE["muted"], "font_size": "11px",
                           "line_height": "1.4"}),
            spacing="1",
            align="start",
        ),
        on_click=AppState.apply_profile(key),
        style={
            "background":    rx.cond(selected, PALETTE["bg"], PALETTE["panel"]),
            "border":        rx.cond(
                selected,
                f"1px solid {PALETTE['accent']}",
                f"1px solid {PALETTE['edge']}",
            ),
            "box_shadow":    rx.cond(
                selected,
                f"0 0 0 1px {PALETTE['accent']} inset",
                "none",
            ),
            "border_radius": "8px",
            "padding":       "8px 10px",
            "min_width":     "160px",
            "flex":          "1",
            "cursor":        "pointer",
            "_hover":        {"border_color": PALETTE["accent"]},
        },
    )


def _wallet_picker() -> rx.Component:
    return rx.hstack(
        rx.foreach(
            AppState.member_rows,
            lambda row: rx.box(
                row["wallet"],
                on_click=AppState.select_wallet(row["wallet"]),
                style={
                    "padding":        "4px 10px",
                    "border_radius":  "999px",
                    "border":         rx.cond(
                        AppState.selected_wallet == row["wallet"],
                        f"1px solid {PALETTE['accent']}",
                        f"1px solid {PALETTE['edge']}",
                    ),
                    "background":     rx.cond(
                        AppState.selected_wallet == row["wallet"],
                        PALETTE["bg"],
                        PALETTE["panel"],
                    ),
                    "color":          rx.cond(
                        AppState.selected_wallet == row["wallet"],
                        PALETTE["accent"],
                        PALETTE["muted"],
                    ),
                    "font_size":      "11px",
                    "font_weight":    rx.cond(
                        AppState.selected_wallet == row["wallet"],
                        "600",
                        "400",
                    ),
                    "cursor":         "pointer",
                    "white_space":    "nowrap",
                    "_hover":         {"border_color": PALETTE["accent"],
                                       "color": PALETTE["text"]},
                },
            ),
        ),
        spacing="2",
        wrap="wrap",
        width="100%",
    )


def _drilldown_card() -> rx.Component:
    return rx.box(
        rx.hstack(
            rx.text("Member drill-down",
                    style={"color": PALETTE["text"], "font_weight": "600",
                           "font_size": "14px"}),
            rx.spacer(),
            rx.cond(
                AppState.loaded,
                rx.hstack(
                    rx.text("Selected:",
                            style={"color": PALETTE["muted"],
                                   "font_size": "11px"}),
                    rx.code(AppState.selected_wallet,
                            style={"color": PALETTE["accent"],
                                   "font_size": "12px"}),
                    spacing="2",
                    align="center",
                ),
                rx.text(""),
            ),
            align="center",
            width="100%",
            margin_bottom="6px",
        ),
        rx.text(
            "Pick a representative profile or any wallet directly to drive "
            "the projection below. The story mode makes member lifecycles "
            "easy to demo in one click.",
            style={"color": PALETTE["muted"], "font_size": "11px",
                   "margin_bottom": "8px"},
        ),
        rx.cond(
            AppState.loaded,
            rx.vstack(
                rx.hstack(
                    *[_profile_chip(k, lbl, d) for k, lbl, d in _PROFILES],
                    spacing="2",
                    width="100%",
                    wrap="wrap",
                ),
                _wallet_picker(),
                rx.hstack(
                    rx.box(
                        rx.text("Current age",
                                style={"color": PALETTE["muted"],
                                       "font_size": "11px"}),
                        rx.text(AppState.member_age_fmt,
                                style={"color": PALETTE["text"],
                                       "font_size": "18px",
                                       "font_weight": "600"}),
                        style={**CARD_STYLE, "flex": "1"},
                    ),
                    rx.box(
                        rx.text("Annual benefit @ retirement",
                                style={"color": PALETTE["muted"],
                                       "font_size": "11px"}),
                        rx.text(AppState.member_first_benefit_fmt,
                                style={"color": PALETTE["text"],
                                       "font_size": "18px",
                                       "font_weight": "600"}),
                        style={**CARD_STYLE, "flex": "1"},
                    ),
                    rx.box(
                        rx.text("Fund @ retirement (det.)",
                                style={"color": PALETTE["muted"],
                                       "font_size": "11px"}),
                        rx.text(AppState.member_fund_peak_fmt,
                                style={"color": PALETTE["text"],
                                       "font_size": "18px",
                                       "font_weight": "600"}),
                        style={**CARD_STYLE, "flex": "1"},
                    ),
                    spacing="2",
                    width="100%",
                ),
                rx.recharts.line_chart(
                    rx.recharts.line(data_key="fund_value",
                                     stroke=PALETTE["accent"],
                                     stroke_width=2, dot=False),
                    rx.recharts.line(data_key="contribution",
                                     stroke=PALETTE["good"],
                                     stroke_width=2, dot=False),
                    rx.recharts.line(data_key="benefit_payment",
                                     stroke=PALETTE["warn"],
                                     stroke_width=2, dot=False),
                    rx.recharts.x_axis(data_key="year",
                                       stroke=PALETTE["muted"]),
                    rx.recharts.y_axis(stroke=PALETTE["muted"]),
                    rx.recharts.cartesian_grid(stroke=PALETTE["edge"]),
                    rx.recharts.legend(),
                    rx.recharts.graphing_tooltip(),
                    data=AppState.member_projection_rows,
                    width="100%",
                    height=280,
                ),
                width="100%",
                spacing="3",
            ),
            rx.text("Load demo data to activate the drill-down.",
                    style={"color": PALETTE["muted"]}),
        ),
        style=CARD_STYLE,
    )


def members_page() -> rx.Component:
    return shell(
        "Members & cohorts",
        "The member register, per-member actuarial valuation and a "
        "story-mode drill-down. Pick a representative profile to demo "
        "the lifecycle at different stages without hunting for a wallet.",
        rx.hstack(
            sidebar_controls(),
            rx.vstack(
                rx.hstack(
                    _roster_card(),
                    _cohort_composition(),
                    spacing="3",
                    width="100%",
                    align="stretch",
                ),
                _valuation_card(),
                _drilldown_card(),
                spacing="3",
                width="100%",
                align="stretch",
            ),
            spacing="3",
            width="100%",
            align="start",
        ),
    )
