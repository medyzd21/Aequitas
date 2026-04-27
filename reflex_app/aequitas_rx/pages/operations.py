"""Operations & Event Feed page."""
from __future__ import annotations

import reflex as rx

from ..components import pill, shell, sidebar_controls, simple_table
from ..state import AppState
from ..theme import CARD_STYLE, PALETTE


def _feed_card() -> rx.Component:
    return rx.box(
        rx.hstack(
            rx.text("Human-readable event feed",
                    style={"color": PALETTE["text"], "font_weight": "600",
                           "font_size": "14px"}),
            rx.spacer(),
            pill("HASH-CHAINED", "good"),
            align="center",
            width="100%",
            margin_bottom="8px",
        ),
        rx.text(
            "Every action the protocol takes is written to a tamper-evident "
            "event log. Each entry links to the previous one via a hash, so "
            "any retroactive edit would break the chain.",
            style={"color": PALETTE["muted"], "font_size": "11px",
                   "margin_bottom": "10px"},
        ),
        rx.cond(
            AppState.event_rows.length() > 0,
            rx.vstack(
                rx.foreach(
                    AppState.event_rows,
                    lambda row: rx.box(
                        rx.hstack(
                            rx.text(
                                "#",
                                style={"color": PALETTE["muted"],
                                       "font_size": "11px"},
                            ),
                            rx.text(
                                row["seq"].to_string(),
                                style={"color": PALETTE["accent"],
                                       "font_size": "12px",
                                       "font_weight": "600"},
                            ),
                            rx.text(
                                row["event"],
                                style={"color": PALETTE["text"],
                                       "font_size": "12px"},
                            ),
                            rx.spacer(),
                            rx.code(
                                row["hash"],
                                style={"color": PALETTE["muted"],
                                       "font_size": "11px"},
                            ),
                            spacing="3",
                            align="center",
                            width="100%",
                        ),
                        style={
                            "padding":       "8px 10px",
                            "border_left":   f"2px solid {PALETTE['accent']}",
                            "background":    PALETTE["bg"],
                            "border_radius": "4px",
                            "margin_bottom": "4px",
                        },
                    ),
                ),
                spacing="1",
                width="100%",
            ),
            rx.text(
                "No events recorded yet. Load the demo dataset or evaluate a "
                "governance proposal to populate the feed.",
                style={"color": PALETTE["muted"]},
            ),
        ),
        style=CARD_STYLE,
    )


def _audit_card() -> rx.Component:
    return rx.box(
        rx.text("Audit chain — raw entries",
                style={"color": PALETTE["text"], "font_weight": "600",
                       "font_size": "14px", "margin_bottom": "4px"}),
        rx.text(
            "Technical appendix: sequence number, event type, payload hash "
            "and the prior-entry hash. This is what a regulator would "
            "replay to verify that nothing has been rewritten.",
            style={"color": PALETTE["muted"], "font_size": "11px",
                   "margin_bottom": "10px"},
        ),
        rx.cond(
            AppState.raw_event_rows.length() > 0,
            simple_table(
                [
                    ("seq",        "#"),
                    ("event_type", "Type"),
                    ("hash",       "Hash"),
                    ("prev_hash",  "Prev hash"),
                ],
                AppState.raw_event_rows,
            ),
            rx.text("—", style={"color": PALETTE["muted"]}),
        ),
        style=CARD_STYLE,
    )


def _bridge_card() -> rx.Component:
    return rx.box(
        rx.hstack(
            rx.text("Bridge to chain",
                    style={"color": PALETTE["text"], "font_weight": "600",
                           "font_size": "14px"}),
            rx.spacer(),
            rx.button(
                "Record bridge hand-off",
                on_click=AppState.record_bridge_handoff,
                color_scheme="indigo",
                size="1",
            ),
            align="center",
            width="100%",
            margin_bottom="6px",
        ),
        rx.text(
            "A hand-off converts the off-chain ledger into the call-list the "
            "Solidity contracts would receive. Use this to log a 'snapshot "
            "was bridged' event in the audit chain.",
            style={"color": PALETTE["muted"], "font_size": "11px"},
        ),
        style=CARD_STYLE,
    )


def operations_page() -> rx.Component:
    return shell(
        "Operations & event feed",
        "Every meaningful action in the protocol — seeds, contributions, "
        "proposals, stress runs, bridge hand-offs — is written to a "
        "hash-chained log so the behaviour of the scheme can be audited "
        "after the fact.",
        rx.hstack(
            sidebar_controls(),
            rx.vstack(
                _feed_card(),
                _bridge_card(),
                _audit_card(),
                spacing="3",
                width="100%",
                align="stretch",
            ),
            spacing="3",
            width="100%",
            align="start",
        ),
    )
