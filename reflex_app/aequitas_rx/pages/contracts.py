"""Contracts / Proof page — product trust center."""
from __future__ import annotations

import reflex as rx

from ..components import pill, shell, simple_table
from ..components_wallet import connect_prompt, protocol_status_banner, wallet_event_bridge
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


def _status_chip(label: str, kind: str = "muted") -> rx.Component:
    return pill(label, kind)


def _hero_summary() -> rx.Component:
    return _panel(
        "Trust center",
        rx.text(
            "This page is where the jury can confirm that Aequitas is not only simulated locally. It shows what is deployed, whether those contracts are verified on Etherscan, which actions have actually been published on-chain, and where to click to confirm the proof.",
            style={"color": PALETTE["text"], "font_size": "13px", "line_height": "1.75"},
        ),
        rx.hstack(
            rx.box(
                rx.cond(
                    AppState.registry_present,
                    _status_chip("Deployed", "good"),
                    _status_chip("Not deployed", "muted"),
                ),
                rx.text(
                    rx.cond(AppState.registry_present, AppState.registry_chain_name, "No deployment registry found"),
                    style={"color": PALETTE["text"], "font_size": "13px", "font_weight": "600", "margin_top": "8px"},
                ),
                rx.text(
                    "Network surfaced from the deployment registry in the repo.",
                    style={"color": PALETTE["muted"], "font_size": "11px", "margin_top": "4px"},
                ),
                style={**CARD_STYLE, "flex": "1 1 0"},
            ),
            rx.box(
                rx.cond(
                    AppState.registry_verified,
                    _status_chip("Verified", "good"),
                    _status_chip("Verification pending", "warn"),
                ),
                rx.text(
                    rx.cond(AppState.registry_present, AppState.registry_rows.length().to_string(), "0"),
                    style={"color": PALETTE["text"], "font_size": "13px", "font_weight": "600", "margin_top": "8px"},
                ),
                rx.text(
                    "Canonical contract addresses surfaced in the UI.",
                    style={"color": PALETTE["muted"], "font_size": "11px", "margin_top": "4px"},
                ),
                style={**CARD_STYLE, "flex": "1 1 0"},
            ),
            rx.box(
                _status_chip(AppState.tx_pill_label, AppState.tx_pill),
                rx.text(
                    rx.cond(AppState.last_tx_short != "", AppState.last_tx_short, "No recent tx"),
                    style={"color": PALETTE["text"], "font_size": "13px", "font_weight": "600", "margin_top": "8px"},
                ),
                rx.text(
                    "Latest wallet-signed action in this session.",
                    style={"color": PALETTE["muted"], "font_size": "11px", "margin_top": "4px"},
                ),
                style={**CARD_STYLE, "flex": "1 1 0"},
            ),
            spacing="3",
            width="100%",
            wrap="wrap",
            align="stretch",
            margin_top="14px",
        ),
        subtitle="Plain English first. Contract names, addresses, and Etherscan proof stay visible, but they no longer dominate the page.",
    )


def _contract_table() -> rx.Component:
    return _panel(
        "What is deployed?",
        rx.cond(
            AppState.registry_present,
            rx.table.root(
                rx.table.header(
                    rx.table.row(
                        rx.table.column_header_cell("Contract"),
                        rx.table.column_header_cell("Address"),
                        rx.table.column_header_cell("Status"),
                        rx.table.column_header_cell("Proof"),
                    ),
                ),
                rx.table.body(
                    rx.foreach(
                        AppState.registry_rows,
                        lambda row: rx.table.row(
                            rx.table.cell(
                                rx.vstack(
                                    rx.text(row["name"], style={"color": PALETTE["text"], "font_size": "12px", "font_weight": "600"}),
                                    rx.text("Verified Sepolia module", style={"color": PALETTE["muted"], "font_size": "11px"}),
                                    spacing="0",
                                    align="start",
                                ),
                            ),
                            rx.table.cell(rx.code(row["short"], style={"font_size": "11px"})),
                            rx.table.cell(
                                rx.cond(
                                    row["verified"] == "yes",
                                    _status_chip("Verified", "good"),
                                    _status_chip("Unverified", "warn"),
                                ),
                            ),
                            rx.table.cell(
                                rx.link(
                                    "View on Etherscan ↗",
                                    href=row["explorer_url"],
                                    is_external=True,
                                    style={"color": PALETTE["accent"], "font_size": "12px"},
                                ),
                            ),
                        ),
                    ),
                ),
                width="100%",
            ),
            rx.text(
                "No deployment registry is available yet, so there is nothing live to verify on-chain from this page.",
                style={"color": PALETTE["muted"], "font_size": "12px"},
            ),
        ),
        subtitle="These are the real Solidity contract names surfaced from the Sepolia deployment registry already present in the repo.",
    )


def _piu_proof_panel() -> rx.Component:
    return _panel(
        "How CPI reaches the protocol",
        rx.text(
            "Aequitas now treats PIU as the inflation-linked pension unit of account. CPI is the economic input, and the publishable on-chain proof is the updated PIU price on CohortLedger.",
            style={"color": PALETTE["text"], "font_size": "12px", "line_height": "1.7"},
        ),
        rx.hstack(
            rx.box(
                _status_chip("Engine input", "muted"),
                rx.text(AppState.current_cpi_fmt, style={"color": PALETTE["text"], "font_size": "15px", "font_weight": "700", "margin_top": "8px"}),
                rx.text("Current CPI level used by the actuarial engine.", style={"color": PALETTE["muted"], "font_size": "11px", "margin_top": "4px"}),
                style={**CARD_STYLE, "flex": "1 1 0"},
            ),
            rx.box(
                _status_chip("Protocol unit", "good"),
                rx.text(AppState.current_piu_price_fmt, style={"color": PALETTE["text"], "font_size": "15px", "font_weight": "700", "margin_top": "8px"}),
                rx.text("Current nominal PIU price implied by that CPI level.", style={"color": PALETTE["muted"], "font_size": "11px", "margin_top": "4px"}),
                style={**CARD_STYLE, "flex": "1 1 0"},
            ),
            rx.box(
                _status_chip("Chain proof", "warn"),
                rx.text("CohortLedger.setPiuPrice", style={"color": PALETTE["text"], "font_size": "15px", "font_weight": "700", "margin_top": "8px"}),
                rx.text("Publishing this step aligns on-chain contribution minting and retirement conversion with the same indexed accounting rule.", style={"color": PALETTE["muted"], "font_size": "11px", "margin_top": "4px"}),
                style={**CARD_STYLE, "flex": "1 1 0"},
            ),
            spacing="3",
            width="100%",
            wrap="wrap",
            align="stretch",
            margin_top="14px",
        ),
        subtitle="Plain English version: CPI changes the PIU price, and the PIU price is what the chain needs in order to verify the indexed accounting rule.",
    )


def _mortality_basis_panel() -> rx.Component:
    return _panel(
        "How mortality learning reaches the protocol",
        rx.text(
            "Aequitas does not put private death records or member histories on-chain. The actuarial engine runs the experience study off-chain, blends the Gompertz prior with observed fund experience using credibility, then publishes only the active mortality basis version and its proof hash.",
            style={"color": PALETTE["text"], "font_size": "12px", "line_height": "1.7"},
        ),
        rx.hstack(
            rx.box(
                _status_chip("Off-chain only", "muted"),
                rx.text("Raw death records, exposures, calibration", style={"color": PALETTE["text"], "font_size": "15px", "font_weight": "700", "margin_top": "8px"}),
                rx.text("Private actuarial work stays off-chain because it is sensitive, bulky, and does not need blockchain to be trusted.", style={"color": PALETTE["muted"], "font_size": "11px", "margin_top": "4px"}),
                style={**CARD_STYLE, "flex": "1 1 0"},
            ),
            rx.box(
                _status_chip("Published on-chain", "good"),
                rx.text("MortalityBasisOracle.publishBasis", style={"color": PALETTE["text"], "font_size": "15px", "font_weight": "700", "margin_top": "8px"}),
                rx.text("The chain only stores the active basis version, cohort digest, credibility score, effective date, and study hash.", style={"color": PALETTE["muted"], "font_size": "11px", "margin_top": "4px"}),
                style={**CARD_STYLE, "flex": "1 1 0"},
            ),
            rx.box(
                rx.cond(
                    AppState.mortality_basis_contract_deployed,
                    _status_chip("Deployed on Sepolia", "good"),
                    _status_chip("Next deployment required", "warn"),
                ),
                rx.text(
                    rx.cond(AppState.mortality_basis_contract_deployed, AppState.registry_chain_name, "MortalityBasisOracle not in current registry"),
                    style={"color": PALETTE["text"], "font_size": "15px", "font_weight": "700", "margin_top": "8px"},
                ),
                rx.text(
                    "Why the chain is needed: it timestamps the active assumption set and prevents silent retroactive rewriting of mortality assumptions.",
                    style={"color": PALETTE["muted"], "font_size": "11px", "margin_top": "4px"},
                ),
                style={**CARD_STYLE, "flex": "1 1 0"},
            ),
            spacing="3",
            width="100%",
            wrap="wrap",
            align="stretch",
            margin_top="14px",
        ),
        rx.hstack(
            rx.box(
                _status_chip("Current snapshot", "muted"),
                rx.text(
                    rx.cond(AppState.sandbox_mortality_basis_version != "", AppState.sandbox_mortality_basis_version, "Not built yet"),
                    style={"color": PALETTE["text"], "font_size": "13px", "font_weight": "600", "margin_top": "8px"},
                ),
                rx.text("Current deterministic mortality basis version in the proof lab.", style={"color": PALETTE["muted"], "font_size": "11px", "margin_top": "4px"}),
                style={**CARD_STYLE, "flex": "1 1 0"},
            ),
            rx.box(
                _status_chip("Proof hash", "warn"),
                rx.text(AppState.sandbox_mortality_study_hash_short, style={"color": PALETTE["text"], "font_size": "13px", "font_weight": "600", "margin_top": "8px"}),
                rx.text("Hash of the off-chain supporting experience study.", style={"color": PALETTE["muted"], "font_size": "11px", "margin_top": "4px"}),
                style={**CARD_STYLE, "flex": "1 1 0"},
            ),
            rx.box(
                _status_chip("What the chain proves", "good"),
                rx.text("Active assumption version", style={"color": PALETTE["text"], "font_size": "13px", "font_weight": "600", "margin_top": "8px"}),
                rx.text("The point is to prove which mortality basis governed later baseline, stress, or reserve publications.", style={"color": PALETTE["muted"], "font_size": "11px", "margin_top": "4px"}),
                style={**CARD_STYLE, "flex": "1 1 0"},
            ),
            spacing="3",
            width="100%",
            wrap="wrap",
            align="stretch",
            margin_top="12px",
        ),
        subtitle="Plain English version: blockchain is used here for the published mortality basis and audit trail, not for sensitive private member data.",
    )


def _actuarial_proof_panel() -> rx.Component:
    return _panel(
        "Actuarial proof layer",
        rx.text(
            "Aequitas does not put the full actuarial engine on-chain. The chain stores the published method versions, parameter hashes, valuation-input commitments, result-bundle commitments, and a small verifier kernel for bounded deterministic spot checks.",
            style={"color": PALETTE["text"], "font_size": "12px", "line_height": "1.7"},
        ),
        rx.hstack(
            rx.box(
                _status_chip("Off-chain engine", "muted"),
                rx.text("Python computes the pension logic in full", style={"color": PALETTE["text"], "font_size": "15px", "font_weight": "700", "margin_top": "8px"}),
                rx.text("Member-by-member valuation loops, mortality fitting, and Monte Carlo stress all stay off-chain.", style={"color": PALETTE["muted"], "font_size": "11px", "margin_top": "4px"}),
                style={**CARD_STYLE, "flex": "1 1 0"},
            ),
            rx.box(
                _status_chip("On-chain registry", "good"),
                rx.text("Method versions and result commitments", style={"color": PALETTE["text"], "font_size": "15px", "font_weight": "700", "margin_top": "8px"}),
                rx.text("The chain timestamps which methods, parameters, and committed inputs governed each published valuation result.", style={"color": PALETTE["muted"], "font_size": "11px", "margin_top": "4px"}),
                style={**CARD_STYLE, "flex": "1 1 0"},
            ),
            rx.box(
                _status_chip("Verifier kernel", "warn"),
                rx.text("Bounded spot checks only", style={"color": PALETTE["text"], "font_size": "15px", "font_weight": "700", "margin_top": "8px"}),
                rx.text("The chain can verify small deterministic claims such as MWR ratios, fairness-corridor checks, and short EPV vectors.", style={"color": PALETTE["muted"], "font_size": "11px", "margin_top": "4px"}),
                style={**CARD_STYLE, "flex": "1 1 0"},
            ),
            spacing="3",
            width="100%",
            wrap="wrap",
            align="stretch",
            margin_top="14px",
        ),
        simple_table(
            [("scope", "Scope"), ("detail", "What this means")],
            AppState.actuarial_proof_scope_rows,
        ),
        rx.hstack(
            rx.box(
                rx.text("Current method families", style={"color": PALETTE["muted"], "font_size": "11px"}),
                rx.text(AppState.actuarial_method_count.to_string(), style={"color": PALETTE["text"], "font_size": "18px", "font_weight": "700", "margin_top": "6px"}),
                rx.text("EPV, MWR, mortality basis, and fairness corridor are versioned separately.", style={"color": PALETTE["muted"], "font_size": "11px", "margin_top": "4px"}),
                style={**CARD_STYLE, "flex": "1 1 0"},
            ),
            rx.box(
                rx.text("Current result bundle", style={"color": PALETTE["muted"], "font_size": "11px"}),
                rx.text(AppState.actuarial_result_contract_key, style={"color": PALETTE["text"], "font_size": "12px", "font_weight": "600", "margin_top": "6px", "word_break": "break-all"}),
                rx.text("Compact commitment tying the current scheme result back to the declared methods and input snapshot.", style={"color": PALETTE["muted"], "font_size": "11px", "margin_top": "4px"}),
                style={**CARD_STYLE, "flex": "1 1 0"},
            ),
            spacing="3",
            width="100%",
            wrap="wrap",
            align="stretch",
            margin_top="12px",
        ),
        simple_table(
            [("family", "Method family"), ("version", "Version"), ("spec_hash_short", "Spec hash"), ("schema_hash_short", "Schema hash")],
            AppState.actuarial_method_rows,
        ),
        simple_table(
            [("label", "Published proof item"), ("value", "Current value")],
            AppState.actuarial_parameter_rows,
        ),
        simple_table(
            [("label", "Result proof item"), ("value", "Current value")],
            AppState.actuarial_result_rows,
        ),
        simple_table(
            [("label", "Verifier check"), ("value", "Current setting")],
            AppState.actuarial_verifier_rows,
        ),
        subtitle="Blockchain is used here for immutable publication, versioning, and bounded spot verification. It is not used to run the whole actuarial engine on-chain.",
    )


def _execution_cost_panel() -> rx.Component:
    return _panel(
        "Execution cost and deployment choice",
        rx.text(
            "This section separates actual chain fees from simulated execution cost. Actual fees show what has already been paid in this session. Simulated cost shows what a much more on-chain operating model would cost if the Twin's actions were really executed at protocol and member level.",
            style={"color": PALETTE["text"], "font_size": "12px", "line_height": "1.7"},
        ),
        rx.hstack(
            rx.box(
                _status_chip("Actual paid so far", "muted"),
                rx.text(AppState.actual_fee_total_fmt, style={"color": PALETTE["text"], "font_size": "15px", "font_weight": "700", "margin_top": "8px"}),
                rx.text("Confirmed wallet-signed fees from this UI session.", style={"color": PALETTE["muted"], "font_size": "11px", "margin_top": "4px"}),
                style={**CARD_STYLE, "flex": "1 1 0"},
            ),
            rx.box(
                _status_chip("Twin Option B", AppState.twin_v2_gas_pill),
                rx.text(AppState.twin_v2_gas_total_fmt, style={"color": PALETTE["text"], "font_size": "15px", "font_weight": "700", "margin_top": "8px"}),
                rx.text("Simulated cumulative blockchain cost from the current Twin run.", style={"color": PALETTE["muted"], "font_size": "11px", "margin_top": "4px"}),
                style={**CARD_STYLE, "flex": "1 1 0"},
            ),
            rx.box(
                _status_chip("Recommendation", AppState.twin_v2_gas_pill),
                rx.text(AppState.twin_v2_gas_recommendation_label, style={"color": PALETTE["text"], "font_size": "15px", "font_weight": "700", "margin_top": "8px"}),
                rx.text(AppState.twin_v2_gas_recommendation_text, style={"color": PALETTE["muted"], "font_size": "11px", "margin_top": "4px", "line_height": "1.6"}),
                style={**CARD_STYLE, "flex": "1 1 0"},
            ),
            spacing="3",
            width="100%",
            wrap="wrap",
            align="stretch",
            margin_top="14px",
        ),
        subtitle="This is where the architecture argument becomes concrete: if broad execution is too expensive under Ethereum-like fees, the honest answer is selective publication or an L2 such as Base.",
    )


def _proof_card(row) -> rx.Component:
    status_kind = rx.cond(
        row["status"] == "CONFIRMED",
        "good",
        rx.cond(
            row["status"] == "PENDING",
            "warn",
            rx.cond(
                (row["status"] == "READY") | (row["status"] == "LOCAL READY") | (row["status"] == "LOCAL PASS"),
                "good",
                rx.cond(row["status"] == "LOCAL FAIL", "bad", "muted"),
            ),
        ),
    )
    return rx.box(
        rx.hstack(
            rx.vstack(
                rx.hstack(
                    rx.text(row["title"], style={"color": PALETTE["text"], "font_size": "13px", "font_weight": "700"}),
                    rx.cond(
                        row["is_live"] == "yes",
                        _status_chip(row["live_label"], "good"),
                        _status_chip(row["live_label"], "muted"),
                    ),
                    _status_chip(row["status"], status_kind),
                    spacing="2",
                    align="center",
                    wrap="wrap",
                ),
                rx.text(row["summary"], style={"color": PALETTE["text"], "font_size": "12px", "line_height": "1.65"}),
                rx.text(row["evidence"], style={"color": PALETTE["muted"], "font_size": "11px"}),
                rx.text(
                    f"Protocol mapping: ",
                    style={"display": "inline"},
                ),
                rx.code(row["contract_function"], style={"font_size": "11px"}),
                rx.text(row["before_after"], style={"color": PALETTE["muted"], "font_size": "11px", "margin_top": "4px"}),
                rx.text(
                    "Estimated model cost: ",
                    row["estimated_cost_label"],
                    " · ",
                    row["estimated_gas_label"],
                    style={"color": PALETTE["muted"], "font_size": "11px", "margin_top": "4px"},
                ),
                rx.text(
                    "Actual signed cost: ",
                    row["actual_cost_label"],
                    " · ",
                    row["actual_gas_label"],
                    style={"color": PALETTE["muted"], "font_size": "11px", "margin_top": "2px"},
                ),
                spacing="1",
                align="start",
            ),
            rx.spacer(),
            rx.vstack(
                rx.cond(
                    row["contract_url"] != "",
                    rx.link("Contract ↗", href=row["contract_url"], is_external=True, style={"color": PALETTE["accent"], "font_size": "11px"}),
                    rx.text("No contract link", style={"color": PALETTE["muted"], "font_size": "11px"}),
                ),
                rx.cond(
                    row["tx_url"] != "",
                    rx.link("Transaction ↗", href=row["tx_url"], is_external=True, style={"color": PALETTE["accent"], "font_size": "11px"}),
                    rx.text("No transaction yet", style={"color": PALETTE["muted"], "font_size": "11px"}),
                ),
                rx.cond(
                    row["key"] == "demo_members",
                    rx.link(
                        rx.button("Open Sandbox", size="1", variant="soft", color_scheme="gray"),
                        href="/sandbox",
                    ),
                    rx.cond(
                        row["is_live"] == "yes",
                        rx.link(
                            rx.button("Open Actions", size="1", variant="soft", color_scheme="cyan"),
                            href="/actions",
                        ),
                        rx.fragment(),
                    ),
                ),
                spacing="2",
                align="end",
            ),
            width="100%",
            align="start",
        ),
        style={
            "padding": "12px 14px",
            "border": f"1px solid {PALETTE['edge']}",
            "border_radius": "12px",
            "background": "rgba(15, 23, 42, 0.42)",
        },
    )


def _verification_flow() -> rx.Component:
    return _panel(
        "What can the jury verify?",
        rx.text(
            "The flow below uses the deterministic Sandbox as the inspection layer and the Actions page as the execution layer. Each row explains what happened, why it matters, and whether there is live Sepolia evidence yet. CPI-linked PIU publication now sits alongside fairness, stress, reserve, and retirement proof.",
            style={"color": PALETTE["text"], "font_size": "12px", "line_height": "1.7", "margin_bottom": "12px"},
        ),
        rx.vstack(
            rx.foreach(AppState.sandbox_action_rows, _proof_card),
            spacing="3",
            width="100%",
        ),
        subtitle="This is the clearest bridge between the actuarial model, the Sandbox proof flow, and the real contracts.",
    )


def _recent_activity() -> rx.Component:
    return _panel(
        "Recent on-chain evidence",
        rx.cond(
            AppState.sandbox_recent_tx_rows.length() > 0,
            simple_table(
                [("action", "Action"), ("short_hash", "Latest tx"), ("fee_label", "Actual fee"), ("status", "Status")],
                AppState.sandbox_recent_tx_rows,
            ),
            rx.text(
                "No live Sepolia transaction has been recorded from this session yet. Use Actions to send one, then return here for the proof trail.",
                style={"color": PALETTE["muted"], "font_size": "12px"},
            ),
        ),
        rx.cond(
            AppState.last_tx_explorer_url != "",
            rx.link(
                "Open the latest transaction on Etherscan ↗",
                href=AppState.last_tx_explorer_url,
                is_external=True,
                style={"color": PALETTE["accent"], "font_size": "12px", "font_weight": "600", "margin_top": "10px"},
            ),
            rx.fragment(),
        ),
        subtitle="This area stays concise so a non-technical reviewer can see whether anything real has happened without reading logs.",
    )


def _verification_notes() -> rx.Component:
    return _panel(
        "How to confirm trust quickly",
        rx.vstack(
            rx.text("1. Check the network and wallet badges at the top of the page.", style={"color": PALETTE["text"], "font_size": "12px"}),
            rx.text("2. Open any contract link to confirm the address and verification status on Etherscan.", style={"color": PALETTE["text"], "font_size": "12px"}),
            rx.text("3. Open Sandbox to inspect the deterministic scheme that produced the proof steps.", style={"color": PALETTE["text"], "font_size": "12px"}),
            rx.text("4. Open Actions to sign a live Sepolia transaction and watch it return here as proof.", style={"color": PALETTE["text"], "font_size": "12px"}),
            spacing="2",
            width="100%",
            align="start",
        ),
        rx.accordion.root(
            rx.accordion.item(
                header=rx.text("Advanced details", style={"color": PALETTE["muted"], "font_size": "11px"}),
                content=rx.vstack(
                    rx.hstack(
                        rx.text("Registry source:", style={"color": PALETTE["muted"], "font_size": "11px"}),
                        rx.code(AppState.registry_source_path, style={"font_size": "11px"}),
                        spacing="2",
                        align="center",
                        width="100%",
                    ),
                    rx.text(
                        "Contract names and Etherscan links are read from the deployment registry, while live action status is synced from the wallet bridge and local event log.",
                        style={"color": PALETTE["muted"], "font_size": "11px", "line_height": "1.6"},
                    ),
                    spacing="2",
                    width="100%",
                    align="start",
                ),
                value="advanced",
            ),
            type="single",
            collapsible=True,
            width="100%",
            margin_top="12px",
        ),
        subtitle="Technical metadata is still available, but only as secondary detail.",
    )


def _developer_tools_panel() -> rx.Component:
    return rx.cond(
        AppState.devtools_enabled,
        _panel(
            "Developer Tools",
            rx.box(
                rx.hstack(
                    pill("DEV ONLY", "warn"),
                    rx.text(
                        "Backend deployment controls for the operator machine. These buttons run local subprocesses and never use MetaMask.",
                        style={"color": PALETTE["text"], "font_size": "12px", "line_height": "1.6"},
                    ),
                    spacing="3",
                    align="center",
                    width="100%",
                ),
                style={
                    "padding": "10px 12px",
                    "border_radius": "12px",
                    "background": PALETTE["edge"],
                    "margin_bottom": "12px",
                },
            ),
            rx.hstack(
                rx.box(
                    rx.cond(
                        AppState.devtools_anvil_detected,
                        _status_chip("Local stack", "good"),
                        _status_chip("Local stack", "warn"),
                    ),
                    rx.text(
                        rx.cond(AppState.devtools_anvil_detected, "Anvil reachable on 127.0.0.1:8545", "Anvil not detected on 127.0.0.1:8545"),
                        style={"color": PALETTE["text"], "font_size": "12px", "font_weight": "600", "margin_top": "8px"},
                    ),
                    rx.text(
                        rx.cond(
                            AppState.devtools_can_deploy_local,
                            "Forge is available and ANVIL_PK is present.",
                            "Needs forge on PATH and ANVIL_PK in the backend environment.",
                        ),
                        style={"color": PALETTE["muted"], "font_size": "11px", "margin_top": "4px"},
                    ),
                    style={**CARD_STYLE, "flex": "1 1 0"},
                ),
                rx.box(
                    rx.cond(
                        AppState.devtools_can_deploy_sepolia,
                        _status_chip("Sepolia", "good"),
                        _status_chip("Sepolia", "warn"),
                    ),
                    rx.text(
                        rx.cond(AppState.devtools_can_deploy_sepolia, "Sepolia deploy env looks ready", "Sepolia deploy env is incomplete"),
                        style={"color": PALETTE["text"], "font_size": "12px", "font_weight": "600", "margin_top": "8px"},
                    ),
                    rx.text(
                        "Requires forge plus DEPLOYER_PK. If SEPOLIA_RPC_URL is not set, forge falls back to its configured sepolia alias.",
                        style={"color": PALETTE["muted"], "font_size": "11px", "margin_top": "4px", "line_height": "1.6"},
                    ),
                    style={**CARD_STYLE, "flex": "1 1 0"},
                ),
                rx.box(
                    _status_chip(AppState.devtools_status_label, AppState.devtools_status_pill),
                    rx.text(
                        rx.cond(AppState.devtools_message != "", AppState.devtools_message, "No developer command has run yet."),
                        style={"color": PALETTE["text"], "font_size": "12px", "font_weight": "600", "margin_top": "8px"},
                    ),
                    rx.text(
                        rx.cond(AppState.devtools_target != "", AppState.devtools_target, "registry"),
                        style={"color": PALETTE["muted"], "font_size": "11px", "margin_top": "4px", "text_transform": "uppercase", "letter_spacing": "0.08em"},
                    ),
                    style={**CARD_STYLE, "flex": "1 1 0"},
                ),
                spacing="3",
                width="100%",
                wrap="wrap",
                align="stretch",
            ),
            rx.hstack(
                rx.vstack(
                    rx.text("Local", style={"color": PALETTE["text"], "font_size": "12px", "font_weight": "700"}),
                    rx.button("Deploy local stack", on_click=AppState.deploy_local_stack, size="2", variant="soft", color_scheme="cyan"),
                    rx.button("Import latest local broadcast", on_click=AppState.import_local_broadcast, size="2", variant="soft", color_scheme="gray"),
                    rx.button("Reload deployment registry", on_click=AppState.reload_deployment_registry, size="2", variant="soft", color_scheme="gray"),
                    spacing="2",
                    align="start",
                    width="100%",
                ),
                rx.vstack(
                    rx.text("Sepolia", style={"color": PALETTE["text"], "font_size": "12px", "font_weight": "700"}),
                    rx.button("Deploy Sepolia stack", on_click=AppState.deploy_sepolia_stack, size="2", variant="soft", color_scheme="cyan"),
                    rx.button("Import latest Sepolia broadcast", on_click=AppState.import_sepolia_broadcast, size="2", variant="soft", color_scheme="gray"),
                    rx.text(
                        "This stays dev-only and reads secrets from the backend environment. It never signs in the browser.",
                        style={"color": PALETTE["muted"], "font_size": "11px", "line_height": "1.6"},
                    ),
                    spacing="2",
                    align="start",
                    width="100%",
                ),
                spacing="4",
                width="100%",
                wrap="wrap",
                align="start",
                margin_top="12px",
            ),
            rx.cond(
                AppState.devtools_last_command != "",
                rx.box(
                    rx.text("Last command", style={"color": PALETTE["muted"], "font_size": "11px", "margin_bottom": "6px"}),
                    rx.code(AppState.devtools_last_command, style={"font_size": "11px", "white_space": "pre-wrap"}),
                    style={**CARD_STYLE, "margin_top": "12px"},
                ),
                rx.fragment(),
            ),
            rx.accordion.root(
                rx.accordion.item(
                    header=rx.text("Command output", style={"color": PALETTE["muted"], "font_size": "11px"}),
                    content=rx.vstack(
                        rx.text(
                            AppState.devtools_log_snippet,
                            style={"color": PALETTE["text"], "font_size": "11px", "white_space": "pre-wrap", "line_height": "1.6"},
                        ),
                        rx.cond(
                            AppState.devtools_logs != "",
                            rx.code(
                                AppState.devtools_logs,
                                style={"font_size": "10px", "white_space": "pre-wrap", "max_height": "280px", "overflow_y": "auto", "width": "100%"},
                            ),
                            rx.fragment(),
                        ),
                        spacing="2",
                        width="100%",
                        align="start",
                    ),
                    value="logs",
                ),
                type="single",
                collapsible=True,
                width="100%",
                margin_top="12px",
            ),
            subtitle="Developer/operator-only deployment controls. Hidden unless AEQUITAS_DEVTOOLS=1 is enabled in the backend environment.",
        ),
        rx.fragment(),
    )


def contracts_page() -> rx.Component:
    return shell(
        "Contracts / Proof",
        "The trust page for Aequitas: what is deployed, what is verified, what has happened on-chain, and where the jury can click to confirm it.",
        wallet_event_bridge(),
        protocol_status_banner(),
        connect_prompt(),
        _hero_summary(),
        _piu_proof_panel(),
        _mortality_basis_panel(),
        _actuarial_proof_panel(),
        _execution_cost_panel(),
        _developer_tools_panel(),
        rx.hstack(
            rx.box(
                _contract_table(),
                _recent_activity(),
                width="100%",
            ),
            rx.box(
                _verification_notes(),
                width="100%",
            ),
            spacing="3",
            width="100%",
            align="start",
            wrap="wrap",
        ),
        _verification_flow(),
        show_demo_disclaimer=False,
        show_deployment_ribbon=False,
        show_kpis=False,
    )
