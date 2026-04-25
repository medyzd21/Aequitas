"""Investment-governance page — member voting on model portfolios."""
from __future__ import annotations

import reflex as rx

from ..components import pill, shell, simple_table
from ..components_wallet import confirm_drawer, connect_prompt, protocol_status_banner, wallet_event_bridge
from ..state import AppState
from ..theme import CARD_STYLE, PALETTE


def _panel(title: str, *children, subtitle: str = "") -> rx.Component:
    return rx.box(
        rx.text(
            title,
            style={"color": PALETTE["text"], "font_weight": "700", "font_size": "15px", "margin_bottom": "4px"},
        ),
        rx.cond(
            subtitle != "",
            rx.text(
                subtitle,
                style={"color": PALETTE["muted"], "font_size": "12px", "margin_bottom": "12px", "line_height": "1.6"},
            ),
            rx.fragment(),
        ),
        *children,
        style={**CARD_STYLE, "margin_bottom": "12px"},
    )


def _mini_stat(label: str, value, note: str) -> rx.Component:
    return rx.box(
        rx.text(label, style={"color": PALETTE["muted"], "font_size": "10px", "text_transform": "uppercase", "letter_spacing": "0.08em"}),
        rx.text(value, style={"color": PALETTE["text"], "font_size": "18px", "font_weight": "700", "margin_top": "4px"}),
        rx.text(note, style={"color": PALETTE["muted"], "font_size": "10px", "margin_top": "4px", "line_height": "1.5"}),
        style={"padding": "10px 12px", "border": f"1px solid {PALETTE['edge']}", "border_radius": "10px", "flex": "1 1 170px", "min_width": "170px"},
    )


def _control_panel() -> rx.Component:
    return rx.box(
        rx.heading("Investment policy sandbox", size="4", style={"color": PALETTE["text"]}),
        rx.text(
            "This page is now a secondary explainer for the deterministic sandbox. The primary investment-governance story lives inside the Digital Twin, where the electorate comes from the simulated member population in that run.",
            style={"color": PALETTE["muted"], "font_size": "11px", "margin_top": "6px", "margin_bottom": "12px", "line_height": "1.6"},
        ),
        rx.box(
            pill("VOTING RULE", "good"),
            rx.text(
                "Every member gets one base vote. Current-period contributions add only a modest concave boost, and no member can exceed 5% of the published ballot weight.",
                style={"color": PALETTE["text"], "font_size": "12px", "margin_top": "8px", "line_height": "1.6"},
            ),
            rx.text(
                "This avoids pure one-member-one-vote and avoids wealth plutocracy. The chain records the snapshot result; it does not infer salary history itself.",
                style={"color": PALETTE["muted"], "font_size": "11px", "margin_top": "8px", "line_height": "1.6"},
            ),
            style={**CARD_STYLE, "margin_bottom": "12px"},
        ),
        rx.text("Ballot actions", style={"color": PALETTE["muted"], "font_size": "11px"}),
        rx.vstack(
            rx.button("Create investment ballot", on_click=AppState.open_action("create_investment_ballot"), color_scheme="cyan", size="2", width="100%"),
            rx.button("Publish weight snapshot", on_click=AppState.open_action("publish_investment_weights"), variant="soft", color_scheme="cyan", size="2", width="100%"),
            rx.button(
                "Finalize ballot",
                on_click=AppState.open_action("finalize_investment_ballot"),
                variant="soft",
                color_scheme="gray",
                size="2",
                width="100%",
            ),
            spacing="2",
            width="100%",
            margin_top="8px",
        ),
        rx.text(
            "The on-chain result is a published investment policy decision. It does not directly buy equities, bonds, gold, or cash instruments.",
            style={"color": PALETTE["muted"], "font_size": "10px", "margin_top": "10px", "line_height": "1.6"},
        ),
        rx.hstack(
            rx.button("Load sandbox electorate", on_click=AppState.load_demo, color_scheme="gray", variant="soft", size="2", width="100%"),
            rx.link(
                rx.button("Open Actions", color_scheme="gray", variant="ghost", size="2", width="100%"),
                href="/actions",
            ),
            spacing="2",
            width="100%",
            margin_top="12px",
        ),
        style={**CARD_STYLE, "width": "320px", "flex_shrink": "0", "position": "sticky", "top": "92px", "align_self": "start"},
    )


def _hero() -> rx.Component:
    return _panel(
        "Investment policy sandbox",
        rx.text(
            "Use this page to inspect the deterministic sandbox version of the ballot mechanics. For the flagship story, open the Digital Twin: ballots now happen inside the simulation, use the run's active contributors as the electorate, and change later-year policy assumptions there.",
            style={"color": PALETTE["text"], "font_size": "13px", "line_height": "1.7"},
        ),
        rx.hstack(
            _mini_stat("Current ballot", AppState.investment_round_name, "Named policy round for the current draft"),
            _mini_stat(
                "Indicative winner",
                rx.cond(AppState.investment_winner_name != "", AppState.investment_winner_name, "—"),
                "Winner under the deterministic sandbox preview",
            ),
            _mini_stat("Winner status", AppState.investment_winner_status_label, "Python guardrail verdict before publication"),
            _mini_stat("Connected wallet", AppState.investment_wallet_weight_fmt, "Your published share in the current ballot snapshot"),
            spacing="3",
            width="100%",
            wrap="wrap",
            align="stretch",
            margin_top="14px",
        ),
        rx.box(
            rx.hstack(
                rx.match(
                    AppState.investment_winner_status_pill,
                    ("good", pill("READY TO PUBLISH", "good")),
                    ("bad", pill("BLOCKED", "bad")),
                    pill("DRAFT", "muted"),
                ),
                rx.text(AppState.investment_winner_reason, style={"color": PALETTE["muted"], "font_size": "12px", "line_height": "1.6"}),
                spacing="3",
                align="center",
                width="100%",
                wrap="wrap",
            ),
            style={"margin_top": "12px"},
        ),
        subtitle="Secondary sandbox surface: useful for inspecting the rule in isolation, but no longer the main product home of investment governance.",
    )


def _portfolio_cards() -> rx.Component:
    return _panel(
        "Model portfolios",
        rx.text(
            "These are the only portfolios on the ballot in this MVP. Members vote on named model portfolios rather than free-form percentages so the choice stays understandable, auditable, and guardrail-checkable.",
            style={"color": PALETTE["muted"], "font_size": "12px", "line_height": "1.65", "margin_bottom": "12px"},
        ),
        rx.hstack(
            rx.foreach(
                AppState.investment_policy_rows,
                lambda row: rx.box(
                    rx.hstack(
                        rx.hstack(
                            pill(row["name"], "muted"),
                            rx.cond(row["is_winner"] == "yes", pill("Indicative winner", "good"), rx.fragment()),
                            spacing="2",
                            align="center",
                            wrap="wrap",
                        ),
                        rx.spacer(),
                        rx.cond(
                            row["validation_kind"] == "good",
                            pill("Passes", "good"),
                            pill("Blocked", "bad"),
                        ),
                        width="100%",
                        align="center",
                    ),
                    rx.text(row["description"], style={"color": PALETTE["text"], "font_size": "13px", "font_weight": "600", "margin_top": "12px"}),
                    rx.text(row["allocation_text"], style={"color": PALETTE["muted"], "font_size": "11px", "margin_top": "8px", "line_height": "1.6"}),
                    rx.hstack(
                        rx.text("Indicative support:", style={"color": PALETTE["text"], "font_size": "12px"}),
                        rx.text(row["support_label"], style={"color": PALETTE["text"], "font_size": "12px", "font_weight": "600"}),
                        spacing="2",
                        align="center",
                        margin_top="12px",
                    ),
                    rx.text(row["reason"], style={"color": PALETTE["muted"], "font_size": "11px", "margin_top": "8px", "line_height": "1.6"}),
                    rx.button(
                        "Cast live vote",
                        on_click=AppState.open_investment_vote_action(row["key"]),
                        color_scheme="cyan",
                        variant="soft",
                        size="2",
                        width="100%",
                        margin_top="12px",
                    ),
                    style={**CARD_STYLE, "flex": "1 1 280px", "min_width": "280px", "height": "100%"},
                ),
            ),
            spacing="3",
            width="100%",
            wrap="wrap",
            align="stretch",
        ),
    )


def _ballot_panels() -> rx.Component:
    return rx.hstack(
        _panel(
            "Current ballot draft",
            simple_table([("label", "Field"), ("value", "Value")], AppState.investment_ballot_rows),
            rx.text(AppState.investment_snapshot_note, style={"color": PALETTE["muted"], "font_size": "11px", "margin_top": "10px", "line_height": "1.6"}),
            subtitle="The Python engine prepares this draft ballot before anything is signed.",
        ),
        _panel(
            "Wallet eligibility",
            rx.hstack(
                rx.match(
                    AppState.wallet_pill,
                    ("good", pill("CONNECTED", "good")),
                    ("warn", pill("WRONG NETWORK", "warn")),
                    pill("NOT CONNECTED", "muted"),
                ),
                rx.match(
                    AppState.investment_winner_status_pill,
                    ("good", pill("WINNER VALID", "good")),
                    ("bad", pill("WINNER BLOCKED", "bad")),
                    pill("NO DRAFT", "muted"),
                ),
                spacing="2",
                align="center",
            ),
            rx.text(
                AppState.investment_wallet_note,
                style={"color": PALETTE["text"], "font_size": "12px", "line_height": "1.65", "margin_top": "10px"},
            ),
            rx.text(
                "If your connected wallet is not part of the deterministic sandbox electorate, you can still inspect the rule, the snapshot, and the publishable payloads.",
                style={"color": PALETTE["muted"], "font_size": "11px", "line_height": "1.6", "margin_top": "10px"},
            ),
            subtitle="This page stays useful even if the juror wallet is not one of the demo members.",
        ),
        spacing="3",
        width="100%",
        align="stretch",
    )


def _support_and_weights() -> rx.Component:
    return rx.hstack(
        _panel(
            "Indicative support",
            simple_table(
                [
                    ("portfolio", "Portfolio"),
                    ("support_label", "Weighted support"),
                    ("validation", "Guardrail verdict"),
                    ("winner", "Outcome"),
                ],
                AppState.investment_support_rows,
            ),
            subtitle="This is the deterministic sandbox preview: one indicative member preference each, weighted by the published snapshot rule.",
        ),
        _panel(
            "Weight snapshot",
            simple_table(
                [
                    ("wallet", "Member"),
                    ("window_contribution_label", "Current-window contribution"),
                    ("vote_share_label", "Published share"),
                    ("published_weight", "On-chain weight"),
                ],
                AppState.investment_weight_rows,
            ),
            subtitle="The snapshot uses current-period contribution flow, not lifetime wealth. That keeps the boost relevant but bounded.",
        ),
        spacing="3",
        width="100%",
        align="stretch",
    )


def _validation_and_boundary() -> rx.Component:
    return rx.hstack(
        _panel(
            "Validation before publication",
            simple_table(
                [
                    ("portfolio", "Portfolio"),
                    ("funded_ratio", "Funded ratio"),
                    ("gini", "Fairness dispersion"),
                    ("stress", "Stress pass rate"),
                    ("verdict", "Verdict"),
                ],
                AppState.investment_validation_rows,
            ),
            rx.text(
                "This is the economic gate. A winning portfolio is only publishable if it stays inside the current funding, fairness, and stress guardrails.",
                style={"color": PALETTE["muted"], "font_size": "11px", "margin_top": "10px", "line_height": "1.6"},
            ),
            subtitle="Serious enough to block unsuitable winners, simple enough to explain to a jury.",
        ),
        _panel(
            "What the chain does and does not do",
            rx.vstack(
                rx.foreach(
                    AppState.investment_assumption_rows,
                    lambda row: rx.box(
                        rx.text(row["note"], style={"color": PALETTE["text"], "font_size": "12px", "line_height": "1.65"}),
                        style={"padding": "10px 0", "border_bottom": f"1px solid {PALETTE['edge']}"},
                    ),
                ),
                spacing="0",
                width="100%",
            ),
            rx.text(
                "Plain English version: blockchain records the ballot, the snapshot, the votes, and the winner. It does not pretend to be an asset manager or custody system.",
                style={"color": PALETTE["muted"], "font_size": "11px", "margin_top": "12px", "line_height": "1.6"},
            ),
            subtitle="The ballot contract is an audit layer for the adopted investment policy, not a brokerage engine.",
        ),
        spacing="3",
        width="100%",
        align="stretch",
    )


def investments_page() -> rx.Component:
    return shell(
        "Investment governance",
        "Member voting on predefined model portfolios with capped concave weights, off-chain guardrail validation, and publishable on-chain ballot outcomes.",
        wallet_event_bridge(),
        protocol_status_banner(),
        connect_prompt(),
        rx.hstack(
            _control_panel(),
            rx.box(
                _hero(),
                _portfolio_cards(),
                _ballot_panels(),
                _support_and_weights(),
                _validation_and_boundary(),
                width="100%",
            ),
            spacing="4",
            width="100%",
            align="start",
        ),
        confirm_drawer(),
        show_demo_disclaimer=False,
        show_deployment_ribbon=False,
    )
