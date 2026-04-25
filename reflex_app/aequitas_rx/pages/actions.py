"""Operator Action Center — `/actions`.

The one place where a non-technical operator can actually operate the
protocol. Each card is a plain-English action; clicking one opens the
shared confirmation drawer (`components_wallet.confirm_drawer`).

Design notes:
* Role columns map directly to the four natural actors: Governance,
  Actuary, Treasury, Auditor. No auth — the roles are a UI grouping.
* `LIVE ON SEPOLIA` tag → the action triggers MetaMask when confirmed.
  `OFF-CHAIN` tag → the action stays in the guided demo flow instead of
  asking the jury member to sign a wallet transaction.
* The confirmation drawer is rendered once at the bottom so it floats
  above the page regardless of which card was clicked.
"""
from __future__ import annotations

import reflex as rx

from ..components import (
    navbar,
    page_header,
    pill,
)
from ..components_wallet import (
    action_card_v2,
    confirm_drawer,
    connect_prompt,
    protocol_status_banner,
    role_column,
    wallet_event_bridge,
)
from ..state import AppState
from ..theme import CARD_STYLE, PALETTE, RIBBON_STYLE


# ==========================================================================
# Role grid
# ==========================================================================
def _governance_cards() -> rx.Component:
    return role_column(
        title="Governance",
        role_tag="Policy",
        blurb="Set the fairness baseline once at inception, then submit "
              "reforms. You can also open a member ballot for the predefined "
              "investment policies. Every proposal is checked by the Python "
              "engine first, then written to the audit chain only if the "
              "guardrails still hold.",
        children=[
            action_card_v2(
                "publish_baseline",
                "Publish cohort baseline",
                "Snapshot the current per-cohort MWR so future proposals "
                "can be measured against it.",
                "LIVE ON SEPOLIA", "FairnessGate",
            ),
            action_card_v2(
                "submit_proposal",
                "Submit governance proposal",
                "Send a reform on-chain — FairnessGate returns PASS or FAIL "
                "against the corridor.",
                "LIVE ON SEPOLIA", "FairnessGate",
            ),
            action_card_v2(
                "create_investment_ballot",
                "Create investment ballot",
                "Open a named member ballot for the predefined growth, balanced, and defensive model portfolios.",
                "LIVE ON SEPOLIA", "InvestmentPolicyBallot",
            ),
            action_card_v2(
                "publish_investment_weights",
                "Publish investment weight snapshot",
                "Write the current decision-window voting snapshot on-chain so the ballot uses capped concave weights instead of lifetime wealth.",
                "LIVE ON SEPOLIA", "InvestmentPolicyBallot",
            ),
            action_card_v2(
                "finalize_investment_ballot",
                "Finalize investment ballot",
                "Close the ballot and publish the winning model portfolio only if the Python guardrail validator says it still passes.",
                rx.cond(AppState.investment_winner_passes, "LIVE ON SEPOLIA", "BLOCKED UNTIL VALID"), "InvestmentPolicyBallot",
            ),
        ],
    )


def _actuary_cards() -> rx.Component:
    return role_column(
        title="Actuary",
        role_tag="Model",
        blurb="Publish CPI-linked accounting inputs, mortality-basis snapshots, "
              "actuarial proof records, and stress-test outputs from the Python engine. "
              "The actuarial model stays the source of truth; the chain records the published versions, commitments, and spot-verifiable claims.",
        children=[
            action_card_v2(
                "publish_piu_price",
                "Publish CPI-linked PIU price",
                "Write the current PIU price on-chain so the ledger uses the same inflation-linked unit accounting as the actuarial engine.",
                "LIVE ON SEPOLIA", "CohortLedger",
            ),
            action_card_v2(
                "publish_mortality_basis",
                "Publish mortality basis snapshot",
                "Timestamp the current experience-based mortality basis so the protocol can prove which survival assumption set governed later decisions.",
                AppState.mortality_basis_mode_label, "MortalityBasisOracle",
            ),
            action_card_v2(
                "publish_actuarial_method",
                "Publish actuarial method version",
                "Write the active actuarial method family, version label, and spec hashes on-chain so published results can point to a declared methodology.",
                AppState.actuarial_method_mode_label, "ActuarialMethodRegistry",
            ),
            action_card_v2(
                "publish_valuation_snapshot",
                "Publish valuation snapshot",
                "Publish the compact parameter snapshot and input commitments for the current valuation without exposing private member records.",
                AppState.actuarial_result_mode_label, "ActuarialResultRegistry",
            ),
            action_card_v2(
                "publish_actuarial_result_bundle",
                "Publish actuarial result bundle",
                "Publish the committed scheme result and link it back to the declared method version, parameter snapshot, and valuation input hashes.",
                AppState.actuarial_result_mode_label, "ActuarialResultRegistry",
            ),
            action_card_v2(
                "publish_stress",
                "Publish fairness stress result",
                "Post the latest Monte Carlo corridor-breach probability to "
                "the StressOracle.",
                "LIVE ON SEPOLIA", "StressOracle",
            ),
            action_card_v2(
                "open_retirement",
                "Open member retirement",
                "Transition a member into decumulation with a sustainable "
                "annual benefit.",
                "LIVE ON SEPOLIA", "VestaRouter",
            ),
        ],
    )


def _treasury_cards() -> rx.Component:
    return role_column(
        title="Treasury",
        role_tag="Capital",
        blurb="Keep the reserve buffer sized against the corridor tail. "
              "Deposits and releases flow through BackstopVault and appear "
              "on the Operations feed.",
        children=[
            action_card_v2(
                "fund_reserve",
                "Fund the reserve vault",
                "Top up BackstopVault so it can cover a future shortfall.",
                "LIVE ON SEPOLIA", "BackstopVault",
            ),
            action_card_v2(
                "release_reserve",
                "Release reserve to cover shortfall",
                "Transfer capital from BackstopVault into LongevaPool when "
                "a shortfall is published.",
                "LIVE ON SEPOLIA", "BackstopVault",
            ),
        ],
    )


def _auditor_cards() -> rx.Component:
    return role_column(
        title="Auditor",
        role_tag="Proof",
        blurb="Supporting steps that stay off-chain. Use these when you "
              "need to prepare or replay the protocol without asking the "
              "jury member to sign a live wallet action.",
        children=[
            action_card_v2(
                "deploy_protocol",
                "Deploy protocol to Sepolia",
                "Prepare the protocol deployment flow that wires all eight "
                "contracts and assigns roles.",
                "OFF-CHAIN", "Setup flow",
            ),
            action_card_v2(
                "demo_flow",
                "Run end-to-end demo flow",
                "Replay the canonical register → contribute → propose → "
                "stress → settle sequence against the live deployment.",
                "OFF-CHAIN", "Replay flow",
            ),
        ],
    )


def _role_grid() -> rx.Component:
    return rx.box(
        rx.hstack(
            _governance_cards(),
            _actuary_cards(),
            _treasury_cards(),
            _auditor_cards(),
            spacing="3",
            width="100%",
            align="stretch",
            wrap="wrap",
        ),
    )


def _start_here_callout() -> rx.Component:
    return rx.cond(
        AppState.registry_present & ~AppState.wallet_connected,
        rx.box(
            rx.hstack(
                pill("START HERE", "good"),
                rx.text(
                    "Start by connecting your wallet, then pick any action from the four columns below.",
                    style={"color": PALETTE["text"], "font_size": "12px"},
                ),
                rx.spacer(),
                rx.button(
                    "Connect wallet",
                    on_click=AppState.connect_wallet,
                    color_scheme="cyan",
                    variant="soft",
                    size="2",
                ),
                spacing="3",
                align="center",
                width="100%",
            ),
            style={
                **RIBBON_STYLE,
                "border_left": f"3px solid {PALETTE['good']}",
                "margin_bottom": "14px",
            },
        ),
        rx.fragment(),
    )


def _product_context_callout() -> rx.Component:
    return rx.box(
        rx.hstack(
            pill("LIVE SEPOLIA ACTIONS", "good"),
            rx.text(
                "Use the Digital Twin to explain the system, the Sandbox to inspect the protocol in miniature, and this page to publish selected real actions on Sepolia.",
                style={"color": PALETTE["text"], "font_size": "12px"},
            ),
            rx.spacer(),
            rx.link(
                "Open Sandbox",
                href="/sandbox",
                style={"color": PALETTE["accent"], "font_size": "12px", "font_weight": "600"},
            ),
            spacing="3",
            align="center",
            width="100%",
        ),
        style={
            **RIBBON_STYLE,
            "border_left": f"3px solid {PALETTE['accent']}",
            "margin_bottom": "14px",
        },
    )


def _execution_cost_callout() -> rx.Component:
    return rx.box(
        rx.hstack(
            pill("EXECUTION COST", AppState.twin_v2_gas_pill),
            rx.text(
                "Actual signed fees and simulated Option B cost are shown separately. Actual fees are what this session has already paid. The Twin estimate is the architecture question: what would a much more on-chain operating model cost under the selected network preset?",
                style={"color": PALETTE["text"], "font_size": "12px"},
            ),
            spacing="3",
            align="start",
            width="100%",
            wrap="wrap",
        ),
        rx.hstack(
            rx.box(
                rx.text("Fee preset", style={"color": PALETTE["muted"], "font_size": "10px", "text_transform": "uppercase", "letter_spacing": "0.08em"}),
                rx.text(AppState.gas_network_label, style={"color": PALETTE["text"], "font_size": "14px", "font_weight": "600", "margin_top": "6px"}),
                rx.select(
                    ["ethereum", "base", "rollup_low"],
                    value=AppState.gas_network_preset,
                    on_change=AppState.change_gas_network_preset,
                    size="2",
                    width="100%",
                    margin_top="8px",
                ),
                rx.text("Switch presets to compare Ethereum-like and L2-style execution without rerunning the actuarial model.", style={"color": PALETTE["muted"], "font_size": "11px", "margin_top": "6px"}),
                style={**CARD_STYLE, "flex": "1 1 0"},
            ),
            rx.box(
                rx.text("Actual signed fees", style={"color": PALETTE["muted"], "font_size": "10px", "text_transform": "uppercase", "letter_spacing": "0.08em"}),
                rx.text(AppState.actual_fee_total_fmt, style={"color": PALETTE["text"], "font_size": "14px", "font_weight": "600", "margin_top": "6px"}),
                rx.text("Confirmed wallet-signed fee total from this session.", style={"color": PALETTE["muted"], "font_size": "11px", "margin_top": "4px"}),
                style={**CARD_STYLE, "flex": "1 1 0"},
            ),
            rx.box(
                rx.text("Twin Option B cost", style={"color": PALETTE["muted"], "font_size": "10px", "text_transform": "uppercase", "letter_spacing": "0.08em"}),
                rx.text(AppState.twin_v2_gas_total_fmt, style={"color": PALETTE["text"], "font_size": "14px", "font_weight": "600", "margin_top": "6px"}),
                rx.text("Cumulative simulated cost from the current Twin run under this preset.", style={"color": PALETTE["muted"], "font_size": "11px", "margin_top": "4px"}),
                style={**CARD_STYLE, "flex": "1 1 0"},
            ),
            spacing="3",
            width="100%",
            wrap="wrap",
            margin_top="12px",
        ),
        style={
            **RIBBON_STYLE,
            "border_left": f"3px solid {PALETTE['warn']}",
            "margin_bottom": "14px",
        },
    )


# ==========================================================================
# Deployment registry block
# ==========================================================================
def _registry_block() -> rx.Component:
    return rx.cond(
        AppState.registry_present,
        rx.box(
            rx.hstack(
                rx.heading("Contract registry", size="4",
                           style={"color": PALETTE["text"]}),
                rx.spacer(),
                rx.hstack(
                    pill(AppState.registry_chain_name, "muted"),
                    rx.cond(
                        AppState.registry_verified,
                        pill("VERIFIED ON ETHERSCAN", "good"),
                        pill("VERIFICATION PENDING", "warn"),
                    ),
                    spacing="2",
                    align="center",
                ),
                align="center",
                width="100%",
            ),
            rx.hstack(
                rx.cond(
                    AppState.registry_deployer != "",
                    rx.hstack(
                        rx.text("Deployed by",
                                style={"color": PALETTE["muted"],
                                       "font_size": "12px"}),
                        rx.link(
                            AppState.registry_deployer,
                            href=AppState.registry_explorer_deployer_url,
                            is_external=True,
                            style={"color": PALETTE["accent"],
                                   "font_size": "12px",
                                   "font_family": "ui-monospace, monospace"},
                        ),
                        rx.cond(
                            AppState.registry_deployed_at != "",
                            rx.hstack(
                                rx.text("·",
                                        style={"color": PALETTE["muted"],
                                               "font_size": "12px"}),
                                rx.text(
                                    AppState.registry_deployed_at,
                                    style={"color": PALETTE["muted"],
                                           "font_size": "12px"},
                                ),
                                spacing="1",
                                align="center",
                            ),
                            rx.fragment(),
                        ),
                        spacing="2",
                        align="center",
                    ),
                    rx.text(
                        "Deployment registered.",
                        style={"color": PALETTE["muted"], "font_size": "12px"},
                    ),
                ),
                margin_top="2px",
                margin_bottom="10px",
            ),
            rx.table.root(
                rx.table.header(
                    rx.table.row(
                        rx.table.column_header_cell("Contract"),
                        rx.table.column_header_cell("Address"),
                        rx.table.column_header_cell("Verified"),
                        rx.table.column_header_cell("Proof"),
                    ),
                ),
                rx.table.body(
                    rx.foreach(
                        AppState.registry_rows,
                        lambda row: rx.table.row(
                            rx.table.cell(row["name"]),
                            rx.table.cell(rx.code(row["short"])),
                            rx.table.cell(
                                rx.cond(
                                    row["verified"] == "yes",
                                    pill("YES", "good"),
                                    pill("NO", "warn"),
                                ),
                            ),
                            rx.table.cell(
                                rx.link(
                                    "Etherscan ↗",
                                    href=row["explorer_url"],
                                    is_external=True,
                                    style={"color": PALETTE["accent"],
                                           "font_size": "12px"},
                                ),
                            ),
                        ),
                    ),
                ),
                width="100%",
            ),
            style={**CARD_STYLE, "margin_top": "14px", "margin_bottom": "14px"},
        ),
        rx.box(
            rx.hstack(
                pill("NO DEPLOYMENT", "muted"),
                rx.text(
                    "The Reflex app did not find a populated registry at "
                    "contracts/deployments/sepolia.json. Run the Sepolia "
                    "deploy flow from the Auditor column to get started.",
                    style={"color": PALETTE["muted"], "font_size": "12px"},
                ),
                spacing="3",
                align="center",
            ),
            style={**RIBBON_STYLE,
                   "border_left": f"3px solid {PALETTE['muted']}",
                   "margin_top": "14px", "margin_bottom": "14px"},
        ),
    )


# ==========================================================================
# Deploy runbook (shown when no deployment exists, OR as a reference tab)
# ==========================================================================
def _deploy_runbook() -> rx.Component:
    return rx.box(
        rx.heading("Deploy runbook", size="4",
                   style={"color": PALETTE["text"]}),
        rx.text(
            "Reflex does not hold your private key — deployment happens "
            "from your shell. Follow these three steps to connect this UI "
            "to a live Sepolia instance:",
            style={"color": PALETTE["muted"], "font_size": "12px",
                   "margin_top": "4px", "margin_bottom": "8px"},
        ),
        rx.ordered_list(
            rx.list_item(
                rx.text.span("Create ",
                             style={"color": PALETTE["text"]}),
                rx.code("contracts/.env",
                        style={"color": PALETTE["accent"]}),
                rx.text.span(" with ",
                             style={"color": PALETTE["text"]}),
                rx.code("SEPOLIA_RPC_URL", style={"color": PALETTE["accent"]}),
                rx.text.span(", ",
                             style={"color": PALETTE["text"]}),
                rx.code("PRIVATE_KEY", style={"color": PALETTE["accent"]}),
                rx.text.span(" and ", style={"color": PALETTE["text"]}),
                rx.code("ETHERSCAN_API_KEY",
                        style={"color": PALETTE["accent"]}),
                rx.text.span(".", style={"color": PALETTE["text"]}),
            ),
            rx.list_item(
                rx.text.span("Run ", style={"color": PALETTE["text"]}),
                rx.code(
                    "forge script script/Deploy.s.sol "
                    "--rpc-url $SEPOLIA_RPC_URL --broadcast --verify",
                    style={"color": PALETTE["accent"]},
                ),
                rx.text.span(".", style={"color": PALETTE["text"]}),
            ),
            rx.list_item(
                rx.text.span("Paste the 8 addresses + tx hashes into ",
                             style={"color": PALETTE["text"]}),
                rx.code("contracts/deployments/sepolia.json",
                        style={"color": PALETTE["accent"]}),
                rx.text.span(". The Reflex app picks it up on reload.",
                             style={"color": PALETTE["text"]}),
            ),
            style={"color": PALETTE["text"], "font_size": "13px",
                   "line_height": "1.7", "padding_left": "20px"},
        ),
        style={**CARD_STYLE, "margin_bottom": "14px"},
    )


# ==========================================================================
# Recent action strip — sits above the role grid
# ==========================================================================
def _recent_action_strip() -> rx.Component:
    return rx.cond(
        AppState.last_tx_status != "idle",
        rx.box(
            rx.hstack(
                rx.match(
                    AppState.tx_pill,
                    ("good", pill("CONFIRMED", "good")),
                    ("warn", pill("PENDING",   "warn")),
                    ("bad",  pill("FAILED",    "bad")),
                    pill("IDLE", "muted"),
                ),
                rx.vstack(
                    rx.text(AppState.last_tx_action,
                            style={"color": PALETTE["text"],
                                   "font_size": "13px",
                                   "font_weight": "600"}),
                    rx.hstack(
                        rx.text(AppState.last_tx_contract,
                                style={"color": PALETTE["muted"],
                                       "font_size": "11px"}),
                        rx.text(".",
                                style={"color": PALETTE["muted"],
                                       "font_size": "11px"}),
                        rx.text(AppState.last_tx_function,
                                style={"color": PALETTE["muted"],
                                       "font_size": "11px"}),
                        spacing="0",
                        align="center",
                    ),
                    spacing="0",
                    align="start",
                ),
                rx.spacer(),
                rx.cond(
                    AppState.last_tx_explorer_url != "",
                    rx.link(
                        rx.hstack(
                            rx.text("View on Etherscan"),
                            rx.text("↗"),
                            spacing="1",
                        ),
                        href=AppState.last_tx_explorer_url,
                        is_external=True,
                        style={"color": PALETTE["accent"],
                               "font_size": "12px"},
                    ),
                    rx.cond(
                        AppState.last_tx_error != "",
                        rx.text(AppState.last_tx_error,
                                style={"color": PALETTE["bad"],
                                       "font_size": "11px",
                                       "max_width": "400px"}),
                        rx.fragment(),
                    ),
                ),
                rx.button(
                    "Clear",
                    on_click=AppState.clear_last_tx,
                    variant="ghost",
                    color_scheme="gray",
                    size="1",
                ),
                spacing="3",
                align="center",
                width="100%",
            ),
            style={**CARD_STYLE, "margin_bottom": "14px"},
        ),
        rx.fragment(),
    )


# ==========================================================================
# Page composition
# ==========================================================================
def actions_page() -> rx.Component:
    return rx.box(
        navbar(),
        rx.box(
            # Hero
            page_header(
                "Operator Action Center",
                "Run selected protocol actions in plain English. Live actions are signed in MetaMask on Sepolia; supporting steps stay off-chain.",
            ),
            # Status banner
            protocol_status_banner(),
            connect_prompt(),
            _recent_action_strip(),
            _product_context_callout(),
            _execution_cost_callout(),
            _start_here_callout(),
            # Role grid
            _role_grid(),
            # Deployment registry
            _registry_block(),
            # Runbook — only shown before Sepolia is populated. Once the
            # registry is in place, a non-technical juror never sees
            # shell instructions by default.
            rx.cond(
                ~AppState.registry_present,
                _deploy_runbook(),
                rx.fragment(),
            ),
            style={
                "max_width": "1400px",
                "margin":    "0 auto",
                "padding":   "20px 24px 64px 24px",
            },
        ),
        # Shared confirmation drawer (rendered once, floats above page)
        confirm_drawer(),
        # Hidden bridge — forwards MetaMask chain/account events into
        # AppState.refresh_wallet_state so the UI stays live.
        wallet_event_bridge(),
        style={
            "background":  PALETTE["bg"],
            "min_height":  "100vh",
            "color":       PALETTE["text"],
            "font_family": "Inter, system-ui, sans-serif",
        },
    )
