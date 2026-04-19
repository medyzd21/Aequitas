"""Home / Fund Overview page."""
from __future__ import annotations

import reflex as rx

from ..components import shell, simple_table, sidebar_controls
from ..state import AppState
from ..theme import CARD_STYLE, PALETTE


def _fund_projection_chart() -> rx.Component:
    return rx.box(
        rx.text("Aggregate fund projection (deterministic)",
                style={"color": PALETTE["text"], "font_weight": "600",
                       "font_size": "14px", "margin_bottom": "8px"}),
        rx.cond(
            AppState.loaded,
            rx.recharts.line_chart(
                rx.recharts.line(data_key="fund_value",
                                 stroke=PALETTE["accent"], stroke_width=2,
                                 dot=False),
                rx.recharts.line(data_key="contributions",
                                 stroke=PALETTE["good"], stroke_width=2,
                                 dot=False),
                rx.recharts.line(data_key="benefit_payments",
                                 stroke=PALETTE["warn"], stroke_width=2,
                                 dot=False),
                rx.recharts.x_axis(data_key="year",
                                   stroke=PALETTE["muted"]),
                rx.recharts.y_axis(stroke=PALETTE["muted"]),
                rx.recharts.cartesian_grid(stroke=PALETTE["edge"]),
                rx.recharts.legend(),
                rx.recharts.graphing_tooltip(),
                data=AppState.fund_projection_rows,
                width="100%",
                height=300,
            ),
            rx.text("Load demo data to see the fund projection.",
                    style={"color": PALETTE["muted"]}),
        ),
        style=CARD_STYLE,
    )


def _cohort_signals() -> rx.Component:
    return rx.box(
        rx.text("Cohort signals",
                style={"color": PALETTE["text"], "font_weight": "600",
                       "font_size": "14px", "margin_bottom": "8px"}),
        rx.cond(
            AppState.cohorts_count >= 2,
            rx.vstack(
                rx.recharts.bar_chart(
                    rx.recharts.bar(data_key="mwr", fill=PALETTE["accent"]),
                    rx.recharts.x_axis(data_key="cohort",
                                       stroke=PALETTE["muted"]),
                    rx.recharts.y_axis(stroke=PALETTE["muted"]),
                    rx.recharts.cartesian_grid(stroke=PALETTE["edge"]),
                    rx.recharts.graphing_tooltip(),
                    data=AppState.cohort_mwr_rows,
                    width="100%",
                    height=240,
                ),
                rx.text(
                    "Bars = MWR per cohort. Parity = 1.00.",
                    style={"color": PALETTE["muted"], "font_size": "11px",
                           "margin_top": "4px"},
                ),
                width="100%",
                align="stretch",
            ),
            rx.text("Need at least two cohorts for a signal read.",
                    style={"color": PALETTE["muted"]}),
        ),
        style=CARD_STYLE,
    )


def _latest_events() -> rx.Component:
    return rx.box(
        rx.text("Latest operations",
                style={"color": PALETTE["text"], "font_weight": "600",
                       "font_size": "14px", "margin_bottom": "8px"}),
        rx.cond(
            AppState.event_rows.length() > 0,
            simple_table(
                [("seq", "#"), ("event", "Event"), ("hash", "Hash")],
                AppState.event_rows,
            ),
            rx.text("No events recorded yet.",
                    style={"color": PALETTE["muted"]}),
        ),
        style=CARD_STYLE,
    )


def overview_page() -> rx.Component:
    return shell(
        "Fund overview",
        "A single page that answers the four questions a regulator asks "
        "first: who is in the scheme, what has been promised, how the "
        "fund is projected to evolve, and where intergenerational stress "
        "is concentrated. Deeper tests and the on-chain surface live in "
        "the other tabs.",
        rx.hstack(
            sidebar_controls(),
            rx.vstack(
                rx.hstack(
                    _fund_projection_chart(),
                    _cohort_signals(),
                    spacing="3",
                    width="100%",
                    align="stretch",
                ),
                _latest_events(),
                spacing="3",
                width="100%",
                align="stretch",
            ),
            spacing="3",
            width="100%",
            align="start",
        ),
    )
