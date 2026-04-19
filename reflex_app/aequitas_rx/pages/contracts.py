"""On-chain surface — real contract names, human-readable action cards.

Each card is titled with the actual Solidity contract and function it
targets (as emitted by `engine.chain_bridge`). The conceptual role is
shown as a subtitle, so the professor always sees both the real
architecture and the meaning in one glance. Raw bridged JSON stays
behind an accordion so the page reads as a product, not a data dump.
"""
from __future__ import annotations

import reflex as rx

from ..components import pill, shell, sidebar_controls, simple_table
from ..state import AppState
from ..theme import CARD_STYLE, PALETTE


# --------------------------------------------------------------------------- small helpers
def _payload_block(payload_var) -> rx.Component:
    return rx.code_block(
        payload_var.to_string(),
        language="json",
        show_line_numbers=False,
        font_size="11px",
        width="100%",
    )


def _payload_list_block(payload_rows) -> rx.Component:
    return rx.code_block(
        payload_rows.to_string(),
        language="json",
        show_line_numbers=False,
        font_size="11px",
        width="100%",
    )


def _action_card(
    contract: str,
    function: str,
    role: str,
    actor: str,
    economic: str,
    actuarial: str,
    payload_body: rx.Component,
) -> rx.Component:
    """Contract-first card: real contract.function at the top, meaning below."""
    return rx.box(
        rx.hstack(
            rx.vstack(
                rx.hstack(
                    rx.code(f"{contract}.{function}",
                            style={"color": PALETTE["accent"],
                                   "font_size": "13px",
                                   "font_weight": "600"}),
                    pill(role, "muted"),
                    spacing="2",
                    align="center",
                ),
                rx.text(actor,
                        style={"color": PALETTE["muted"],
                               "font_size": "11px", "margin_top": "2px"}),
                spacing="0",
                align="start",
            ),
            rx.spacer(),
            pill("BRIDGED", "good"),
            align="center",
            width="100%",
            margin_bottom="10px",
        ),
        rx.text(
            rx.text.strong("What it does: ",
                           style={"color": PALETTE["accent"]}),
            economic,
            style={"color": PALETTE["text"], "font_size": "12px",
                   "line_height": "1.5"},
        ),
        rx.text(
            rx.text.strong("Actuarial meaning: ",
                           style={"color": PALETTE["accent"]}),
            actuarial,
            style={"color": PALETTE["muted"], "font_size": "12px",
                   "line_height": "1.5", "margin_top": "4px"},
        ),
        rx.accordion.root(
            rx.accordion.item(
                header=rx.text(
                    "Raw bridged payload (technical appendix)",
                    style={"color": PALETTE["muted"], "font_size": "11px"},
                ),
                content=payload_body,
                value="payload",
            ),
            collapsible=True,
            type="single",
            width="100%",
            margin_top="8px",
        ),
        style={**CARD_STYLE,
               "border_left": f"3px solid {PALETTE['accent']}",
               "margin_bottom": "10px"},
    )


# --------------------------------------------------------------------------- top section
def _deployment_card() -> rx.Component:
    return rx.box(
        rx.hstack(
            rx.text("Deployment state",
                    style={"color": PALETTE["text"], "font_weight": "600",
                           "font_size": "14px"}),
            rx.spacer(),
            rx.cond(
                AppState.deployment_detected,
                pill("ON-CHAIN CONNECTED", "good"),
                pill("OFF-CHAIN ONLY", "muted"),
            ),
            align="center",
            width="100%",
            margin_bottom="8px",
        ),
        rx.text(
            "Aequitas ships as eight Solidity contracts. When a local "
            "Anvil/Foundry deployment is detected via "
            "`engine.deployments.load_latest()`, the deployed addresses "
            "populate the table below. Otherwise this terminal runs in "
            "pure off-chain simulation mode — the actuarial engine is "
            "still the source of truth in both modes.",
            style={"color": PALETTE["muted"], "font_size": "11px",
                   "margin_bottom": "10px"},
        ),
        rx.cond(
            AppState.deployment_detected,
            simple_table(
                [("contract", "Contract"), ("address", "Address")],
                AppState.deployment_address_rows,
            ),
            rx.text(
                "No deployment detected. From the repo root run "
                "`forge script script/Deploy.s.sol --rpc-url localhost "
                "--broadcast` to connect this terminal to a live stack.",
                style={"color": PALETTE["muted"], "font_size": "11px"},
            ),
        ),
        style=CARD_STYLE,
    )


# --------------------------------------------------------------------------- action cards (real contract names)
def _cohort_ledger_cards() -> rx.Component:
    return rx.vstack(
        _action_card(
            contract="CohortLedger",
            function="registerMember + contribute",
            role="Membership + PIU accounting",
            actor="Member wallet → CohortLedger",
            economic=(
                "Admits a wallet into the scheme and records each contribution "
                "as a mint of Pension Inflation Units (PIUs). PIUs preserve "
                "real purchasing power through accumulation and are the "
                "unit of account the rest of the protocol reads."
            ),
            actuarial=(
                "Establishes (age x, retirement age r, cohort c) and feeds "
                "EPV(contributions) = Σ vᵗ · ₜpₓ · Cₜ. The PIU balance is what "
                "LongevaPool later converts into a life annuity."
            ),
            payload_body=_payload_list_block(AppState.ledger_payload_preview),
        ),
        spacing="2",
        width="100%",
        align="stretch",
    )


def _fairness_gate_cards() -> rx.Component:
    return rx.vstack(
        _action_card(
            contract="FairnessGate",
            function="setBaseline",
            role="Corridor baseline",
            actor="Python fairness engine → FairnessGate",
            economic=(
                "Snapshots per-cohort EPV(benefits), EPV(contributions) and "
                "MWR on-chain. Every future proposal is measured as a delta "
                "against this reference line."
            ),
            actuarial=(
                "This is the 'before' state of the corridor test. Without a "
                "baseline, the governance gate has nothing to compare against."
            ),
            payload_body=_payload_block(AppState.baseline_payload),
        ),
        _action_card(
            contract="FairnessGate",
            function="submitAndEvaluate",
            role="Governance gate",
            actor="Governance sandbox → FairnessGate",
            economic=(
                "A proposal only reaches Timelock if its benefit-multiplier "
                "change keeps the MWR shift inside the fairness corridor δ. "
                "Failing proposals are rejected at this contract."
            ),
            actuarial=(
                "Corridor rule: max‖ΔMWRᵢ − ΔMWRⱼ‖ / parity ≤ δ. Prevents "
                "one generation from being made disproportionately worse "
                "off than its neighbour."
            ),
            payload_body=_payload_block(AppState.proposal_payload),
        ),
        spacing="2",
        width="100%",
        align="stretch",
    )


def _longeva_retirement_cards() -> rx.Component:
    return rx.vstack(
        _action_card(
            contract="VestaRouter",
            function="openRetirement",
            role="Accumulation → decumulation router",
            actor="Retiring member → VestaRouter",
            economic=(
                "Flips the member from accumulation into decumulation, locks "
                "the annual benefit B_r, and hands the member's PIU balance "
                "over to LongevaPool. BenefitStreamer then pays out."
            ),
            actuarial=(
                "Locks the replacement ratio and the projected annual benefit "
                "computed from final salary and accrued PIUs. This is the "
                "pivot from the contributions side of EPV to the benefits side."
            ),
            payload_body=_payload_block(AppState.open_retirement_payload),
        ),
        _action_card(
            contract="LongevaPool",
            function="deposit",
            role="Longevity pool",
            actor="VestaRouter → LongevaPool",
            economic=(
                "The retiree's PIU balance is pooled. The pool survives them: "
                "the remainder finances the survivor stream for the rest of "
                "the cohort. MortalityOracle publishes the survival curve "
                "that prices each deposit."
            ),
            actuarial=(
                "Converts accumulation-phase capital into a life annuity "
                "priced off ₜpₓ. Individual longevity risk becomes a pooled "
                "cohort risk with liability Σ ₜpₓ · Bₜ."
            ),
            payload_body=_payload_block(AppState.pool_deposit_payload),
        ),
        spacing="2",
        width="100%",
        align="stretch",
    )


def _stress_backstop_cards() -> rx.Component:
    return rx.vstack(
        _action_card(
            contract="StressOracle",
            function="updateStressLevel",
            role="Fairness telemetry",
            actor="Python stress engine → StressOracle",
            economic=(
                "Publishes the Monte-Carlo fairness-stress result on-chain — "
                "corridor pass rate, p95 Gini, worst-affected cohort — so "
                "downstream contracts can react before the stress materialises."
            ),
            actuarial=(
                "One-factor cohort shock: m_c(s) = 1 + β_c·F(s) + ε_c(s). "
                "β is loaded so younger cohorts bear more systemic risk than "
                "retirees — an explicit intergenerational choice."
            ),
            payload_body=_payload_block(AppState.stress_update_payload),
        ),
        _action_card(
            contract="BackstopVault",
            function="deposit",
            role="Reserve top-up",
            actor="Treasury → BackstopVault",
            economic=(
                "Tops up the reserve that absorbs shortfalls when realised "
                "returns fall short of what the fairness corridor requires."
            ),
            actuarial=(
                "Sized against the tail of the fund-value distribution — the "
                "gap between p5 realised EPV(benefits) coverage and the "
                "target funded ratio."
            ),
            payload_body=_payload_block(AppState.backstop_deposit_payload),
        ),
        _action_card(
            contract="BackstopVault",
            function="release",
            role="Stress-gated release",
            actor="BackstopVault → CohortLedger",
            economic=(
                "Transfers reserves back into the main pool when StressOracle "
                "reports a breach, preserving promised benefits through a "
                "stress event instead of forcing a discretionary cut."
            ),
            actuarial=(
                "Release is condition-gated on the StressOracle state: only "
                "fires if the published p95 Gini or youngest-poor rate "
                "breaches the policy threshold."
            ),
            payload_body=_payload_block(AppState.backstop_release_payload),
        ),
        spacing="2",
        width="100%",
        align="stretch",
    )


# --------------------------------------------------------------------------- sectioning
def _section_title(title: str, subtitle: str) -> rx.Component:
    return rx.box(
        rx.text(title,
                style={"color": PALETTE["text"], "font_weight": "600",
                       "font_size": "13px", "letter_spacing": "0.02em"}),
        rx.text(subtitle,
                style={"color": PALETTE["muted"], "font_size": "11px",
                       "margin_top": "2px"}),
        style={"margin_top": "4px", "margin_bottom": "4px"},
    )


def contracts_page() -> rx.Component:
    return shell(
        "On-chain surface",
        "Eight Solidity contracts and the Python calls that drive them. "
        "Each card is titled with the real contract and function — same "
        "names you'd see on-chain — plus its conceptual role. Raw "
        "bridged JSON is tucked behind each expander.",
        rx.hstack(
            sidebar_controls(),
            rx.vstack(
                _deployment_card(),
                _section_title(
                    "1 · Membership + contributions",
                    "CohortLedger — on-chain register and PIU accounting.",
                ),
                _cohort_ledger_cards(),
                _section_title(
                    "2 · Fairness & governance",
                    "FairnessGate — baseline snapshot + corridor "
                    "evaluation that gates every proposal.",
                ),
                _fairness_gate_cards(),
                _section_title(
                    "3 · Retirement & longevity pool",
                    "VestaRouter → LongevaPool (priced off MortalityOracle). "
                    "BenefitStreamer does the periodic payouts.",
                ),
                _longeva_retirement_cards(),
                _section_title(
                    "4 · Stress oracle & backstop",
                    "StressOracle telemetry gates BackstopVault releases.",
                ),
                _stress_backstop_cards(),
                spacing="3",
                width="100%",
                align="stretch",
            ),
            spacing="3",
            width="100%",
            align="start",
        ),
    )
