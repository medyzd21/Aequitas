"""Product homepage — Digital Twin first, Sandbox second."""
from __future__ import annotations

import reflex as rx

from ..components import pill, shell
from ..state import AppState
from ..theme import CARD_STYLE, PALETTE


def _hero_tile(label: str, value, note: str) -> rx.Component:
    return rx.box(
        rx.text(
            label,
            style={
                "color": PALETTE["muted"],
                "font_size": "10px",
                "letter_spacing": "0.08em",
                "text_transform": "uppercase",
                "margin_bottom": "6px",
            },
        ),
        rx.text(
            value,
            style={"color": PALETTE["text"], "font_size": "24px", "font_weight": "700"},
        ),
        rx.text(
            note,
            style={"color": PALETTE["muted"], "font_size": "11px", "margin_top": "4px"},
        ),
        style={**CARD_STYLE, "flex": "1 1 0", "min_width": "170px"},
    )


def _destination_card(
    eyebrow: str,
    title: str,
    body: str,
    href: str,
    cta: str,
    badge: str,
    badge_kind: str,
) -> rx.Component:
    return rx.link(
        rx.box(
            rx.hstack(
                pill(eyebrow, "muted"),
                rx.spacer(),
                pill(badge, badge_kind),
                width="100%",
                align="center",
            ),
            rx.heading(
                title,
                size="4",
                style={"color": PALETTE["text"], "margin_top": "12px", "margin_bottom": "8px"},
            ),
            rx.text(
                body,
                style={"color": PALETTE["muted"], "font_size": "13px", "line_height": "1.65"},
            ),
            rx.hstack(
                rx.text(
                    cta,
                    style={
                        "color": PALETTE["accent"],
                        "font_size": "12px",
                        "font_weight": "600",
                    },
                ),
                rx.text("→", style={"color": PALETTE["accent"], "font_size": "12px"}),
                spacing="2",
                align="center",
                margin_top="14px",
            ),
            style={
                **CARD_STYLE,
                "height": "100%",
                "transition": "transform 0.18s ease, border-color 0.18s ease",
                "_hover": {
                    "transform": "translateY(-2px)",
                    "border_color": PALETTE["accent"],
                },
            },
        ),
        href=href,
        style={"text_decoration": "none", "flex": "1 1 0", "min_width": "260px"},
    )


def _run_summary_card() -> rx.Component:
    return rx.box(
        rx.hstack(
            rx.vstack(
                rx.hstack(
                    pill("Flagship experience", "good"),
                    rx.match(
                        AppState.twin_v2_fairness_pill,
                        ("good", pill("Stable run", "good")),
                        ("warn", pill("Pressure building", "warn")),
                        ("bad", pill("Stressed run", "bad")),
                        pill("Not run yet", "muted"),
                    ),
                    spacing="2",
                    align="center",
                    wrap="wrap",
                ),
                rx.heading(
                    "Digital Twin",
                    size="6",
                    style={"color": PALETTE["text"], "margin_top": "8px"},
                ),
                rx.text(
                    "A large synthetic pension society that evolves year by year under demographic change, investment shocks, fund-linked PIU accounting, experience-based mortality learning, fairness pressure, and governance responses.",
                    style={"color": PALETTE["muted"], "font_size": "13px", "line_height": "1.7"},
                ),
                spacing="1",
                align="start",
            ),
            rx.spacer(),
            rx.link(
                rx.button(
                    "Open Digital Twin",
                    color_scheme="cyan",
                    size="3",
                ),
                href="/twin",
            ),
            width="100%",
            align="center",
        ),
        rx.cond(
            AppState.twin_v2_ran,
            rx.vstack(
                rx.text(
                    AppState.twin_v2_run_summary,
                    style={
                        "color": PALETTE["text"],
                        "font_size": "13px",
                        "line_height": "1.75",
                        "margin_top": "14px",
                    },
                ),
                rx.hstack(
                    rx.foreach(
                        AppState.twin_v2_run_highlights,
                        lambda row: _hero_tile(
                            row["label"],
                            row["value"],
                            "Latest run snapshot",
                        ),
                    ),
                    spacing="3",
                    width="100%",
                    wrap="wrap",
                    align="stretch",
                ),
                spacing="3",
                width="100%",
            ),
            rx.box(
                rx.text(
                    "Run the Digital Twin to generate a narrative summary, event history, fairness view, representative stories, and the on-chain mapping for the simulated society.",
                    style={
                        "color": PALETTE["muted"],
                        "font_size": "13px",
                        "line_height": "1.7",
                        "margin_top": "14px",
                    },
                ),
            ),
        ),
        style={
            **CARD_STYLE,
            "padding": "20px 22px",
            "background": "linear-gradient(135deg, rgba(17,26,46,0.98), rgba(8,47,73,0.78))",
            "border": f"1px solid {PALETTE['edge']}",
        },
    )


def _two_layer_story() -> rx.Component:
    return rx.box(
        rx.hstack(
            rx.box(
                pill("1", "good"),
                rx.heading("Digital Twin", size="4", style={"color": PALETTE["text"], "margin_top": "10px"}),
                rx.text(
                    "The main product. Explore a synthetic pension society at scale, with heterogeneity, fund-linked PIU accounting, mortality learning, shocks, governance proposals, fairness metrics, and representative member stories.",
                    style={"color": PALETTE["muted"], "font_size": "12px", "line_height": "1.65", "margin_top": "8px"},
                ),
                style={**CARD_STYLE, "flex": "1 1 0"},
            ),
            rx.box(
                pill("2", "warn"),
                rx.heading("Sandbox", size="4", style={"color": PALETTE["text"], "margin_top": "10px"}),
                rx.text(
                    "The proof lab. Use the deterministic small scheme to inspect member-level values, PIU minting, indexed pension conversion, test proposals before and after, and verify selected steps against live Sepolia contracts.",
                    style={"color": PALETTE["muted"], "font_size": "12px", "line_height": "1.65", "margin_top": "8px"},
                ),
                style={**CARD_STYLE, "flex": "1 1 0"},
            ),
            spacing="3",
            width="100%",
            align="stretch",
            wrap="wrap",
        ),
        style={"margin_top": "2px"},
    )


def _trust_row() -> rx.Component:
    return rx.hstack(
        _hero_tile(
            "Network",
            rx.cond(AppState.registry_present, AppState.registry_chain_name, "Not connected"),
            "Deployment registry detected from the repo",
        ),
        _hero_tile(
            "Contracts",
            rx.cond(AppState.registry_present, AppState.registry_rows.length().to_string(), "0"),
            "Canonical Solidity contracts surfaced in the UI",
        ),
        _hero_tile(
            "Verification",
            rx.cond(AppState.registry_verified, "Verified", "Pending"),
            "Etherscan verification status from sepolia.json",
        ),
        _hero_tile(
            "Latest proof",
            rx.cond(AppState.last_tx_short != "", AppState.last_tx_short, "No recent tx"),
            "Most recent wallet action recorded in this session",
        ),
        spacing="3",
        width="100%",
        wrap="wrap",
        align="stretch",
    )


def _journey_card() -> rx.Component:
    steps = [
        ("Open Digital Twin", "Show the pension system evolving at scale under shocks and governance pressure."),
        ("Switch to Sandbox", "Inspect a small deterministic scheme so every member, cohort, and proposal can be explained."),
        ("Sign a live action", "Use Actions to publish a selected Sepolia transaction with MetaMask."),
        ("Open Contracts / Proof", "Show deployed addresses, verification status, and Etherscan links for confirmation."),
    ]
    return rx.box(
        rx.heading("Recommended jury flow", size="4", style={"color": PALETTE["text"], "margin_bottom": "10px"}),
        rx.vstack(
            *[
                rx.hstack(
                    rx.box(
                        f"{idx}.",
                        style={
                            "color": PALETTE["bg"],
                            "background": PALETTE["accent"],
                            "padding": "4px 8px",
                            "border_radius": "999px",
                            "font_weight": "700",
                            "font_size": "12px",
                            "min_width": "28px",
                            "text_align": "center",
                        },
                    ),
                    rx.vstack(
                        rx.text(title, style={"color": PALETTE["text"], "font_size": "13px", "font_weight": "600"}),
                        rx.text(body, style={"color": PALETTE["muted"], "font_size": "12px", "line_height": "1.6"}),
                        spacing="1",
                        align="start",
                    ),
                    spacing="3",
                    align="start",
                    width="100%",
                )
                for idx, (title, body) in enumerate(steps, start=1)
            ],
            spacing="3",
            width="100%",
            align="stretch",
        ),
        style={**CARD_STYLE, "height": "100%"},
    )


def _proof_snapshot() -> rx.Component:
    return rx.box(
        rx.heading("What the chain proves", size="4", style={"color": PALETTE["text"], "margin_bottom": "10px"}),
        rx.text(
            "Aequitas does not ask the jury to trust a hidden black box. The Sandbox and Actions surfaces expose which steps are simulated locally, which are publishable on-chain, and where the verified Sepolia proof lives.",
            style={"color": PALETTE["muted"], "font_size": "12px", "line_height": "1.7", "margin_bottom": "12px"},
        ),
        rx.vstack(
            rx.foreach(
                AppState.sandbox_action_rows,
                lambda row: rx.hstack(
                    rx.match(
                        row["status"],
                        ("CONFIRMED", pill(row["status"], "good")),
                        ("READY", pill(row["status"], "good")),
                        ("LOCAL READY", pill(row["status"], "good")),
                        ("LOCAL PASS", pill(row["status"], "good")),
                        ("PENDING", pill(row["status"], "warn")),
                        pill(row["status"], "muted"),
                    ),
                    rx.text(row["title"], style={"color": PALETTE["text"], "font_size": "12px", "font_weight": "600"}),
                    rx.spacer(),
                    rx.text(row["contract_function"], style={"color": PALETTE["muted"], "font_size": "11px"}),
                    spacing="3",
                    align="center",
                    width="100%",
                ),
            ),
            spacing="2",
            width="100%",
            align="stretch",
        ),
        rx.link(
            "Open Contracts / Proof →",
            href="/contracts",
            style={"color": PALETTE["accent"], "font_size": "12px", "font_weight": "600", "margin_top": "12px"},
        ),
        style={**CARD_STYLE, "height": "100%"},
    )


def _destination_grid() -> rx.Component:
    return rx.hstack(
        _destination_card(
            "Core",
            "Digital Twin",
            "Configure and run a synthetic pension society over time. This is the flagship analytical experience and the main demonstration surface.",
            "/twin",
            "Open the flagship simulator",
            "Main product",
            "good",
        ),
        _destination_card(
            "Proof lab",
            "Sandbox",
            "Walk through the small deterministic scheme with roster, per-member values, fairness before and after, and on-chain proof steps.",
            "/sandbox",
            "Open the deterministic lab",
            "Inspectable",
            "warn",
        ),
        _destination_card(
            "Policy voting",
            "Investments",
            "Show how members choose between predefined growth, balanced, and defensive model portfolios with capped concave voting weights and Python-side guardrails.",
            "/investments",
            "Open investment governance",
            "Member-governed",
            "good",
        ),
        _destination_card(
            "Live actions",
            "Actions",
            "Ask MetaMask to sign selected live Sepolia actions with clear confirmation, pending, confirmed, and Etherscan states.",
            "/actions",
            "Open the action center",
            "Executable",
            "good",
        ),
        spacing="3",
        width="100%",
        align="stretch",
        wrap="wrap",
    )


def overview_page() -> rx.Component:
    return shell(
        "Pension intelligence, backed by proof",
        "Aequitas now tells one clear story: the Digital Twin explains how a pension system behaves at scale, and the Sandbox proves the protocol is inspectable and real on Sepolia.",
        _run_summary_card(),
        _two_layer_story(),
        _trust_row(),
        _destination_grid(),
        rx.hstack(
            _journey_card(),
            _proof_snapshot(),
            spacing="3",
            width="100%",
            align="stretch",
            wrap="wrap",
        ),
        show_demo_disclaimer=False,
        show_deployment_ribbon=False,
        show_kpis=False,
    )
