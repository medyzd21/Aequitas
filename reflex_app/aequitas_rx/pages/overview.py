"""Product homepage — investor-facing overview of Aequitas."""
from __future__ import annotations

import reflex as rx

from ..components import pill, shell
from ..state import AppState
from ..theme import CARD_STYLE, PALETTE


def _hero_cta() -> rx.Component:
    """Top-of-page investor hero with clear statement and CTA buttons."""
    return rx.box(
        rx.heading(
            "Aequitas is pension intelligence with public proof.",
            size="7",
            style={"color": PALETTE["text"], "line_height": "1.25",
                   "margin_bottom": "10px"},
        ),
        rx.text(
            "Python computes the pension economics. "
            "Blockchain records the audit trail.",
            style={"color": PALETTE["muted"], "font_size": "16px",
                   "line_height": "1.5", "margin_bottom": "24px"},
        ),
        rx.hstack(
            rx.link(
                rx.button("Run Digital Twin V2", color_scheme="indigo", size="3"),
                href="/twin",
            ),
            rx.link(
                rx.button("Join as a member", variant="soft",
                          color_scheme="indigo", size="3"),
                href="/members",
            ),
            rx.link(
                rx.button("View proof layer", variant="outline",
                          color_scheme="gray", size="3"),
                href="/contracts",
            ),
            spacing="3",
            wrap="wrap",
            align="center",
        ),
        style={"padding": "32px 0 28px 0"},
    )


_VALUE_CARDS = [
    (
        "Digital Twin",
        "A 40-year simulation of a synthetic pension society. "
        "The Python actuarial engine runs year by year with shocks, "
        "governance responses, and cohort-level fairness tracking.",
    ),
    (
        "Non-transferable PIUs",
        "Members accumulate Pension Investment Units priced at smoothed fund NAV "
        "per active supply. PIUs are non-transferable and not redeemable before "
        "retirement — not a token, not an NFT.",
    ),
    (
        "Fairness Gate",
        "Every reform proposal is evaluated on-chain against the "
        "intergenerational MWR corridor before it can execute. "
        "Disproportionate harm to any generation is blocked.",
    ),
    (
        "On-chain audit trail",
        "Private data stays off-chain. Method versions, parameter hashes, "
        "and valuation commitments go on-chain — a public, tamper-evident "
        "record of how the scheme was run.",
    ),
    (
        "Member onboarding",
        "New members apply here. Estimated annual contribution and "
        "first-year PIUs update live as you type. "
        "Personal details stay off-chain in this prototype.",
    ),
]


def _value_cards() -> rx.Component:
    """Five investor-facing value proposition cards."""
    return rx.hstack(
        *[
            rx.box(
                rx.text(
                    title,
                    style={"color": PALETTE["text"], "font_size": "13px",
                           "font_weight": "700", "margin_bottom": "8px"},
                ),
                rx.text(
                    body,
                    style={"color": PALETTE["muted"], "font_size": "12px",
                           "line_height": "1.65"},
                ),
                style={**CARD_STYLE, "flex": "1 1 0", "min_width": "180px"},
            )
            for title, body in _VALUE_CARDS
        ],
        spacing="3",
        width="100%",
        align="stretch",
        wrap="wrap",
    )


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
                    color_scheme="indigo",
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
        ("Open Digital Twin", "Run the pension simulation at scale — shocks, governance responses, fairness tracking, and the on-chain mapping in one view."),
        ("Join / Members", "See how members onboard. Estimated PIUs at the current fund-linked price. Personal details stay off-chain in this prototype."),
        ("Open Sandbox", "Inspect the small deterministic proof lab — every member value, fairness proposal, and Sepolia transaction visible and clickable."),
        ("Open Contracts / Proof", "Confirm deployed addresses, Etherscan verification, and the public audit trail."),
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
            "Aequitas does not ask anyone to trust a hidden black box. The Sandbox and Actions surfaces expose which steps are simulated locally, which are publishable on-chain, and where the verified Sepolia proof lives.",
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
        _destination_card(
            "Onboarding",
            "Join as a member",
            "New members can apply to join Aequitas here. Fill in personal details, see your estimated annual contribution and first-year PIUs, then submit a demo application.",
            "/members",
            "Open the membership portal",
            "Open to new members",
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
        "An off-chain actuarial engine paired with on-chain proof commitments — pension economics made transparent and auditable.",
        _hero_cta(),
        _value_cards(),
        _run_summary_card(),
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
