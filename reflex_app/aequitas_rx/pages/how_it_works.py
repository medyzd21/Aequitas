"""How Aequitas Works — professor-facing narrative.

Three parts:
  (1) an 8-step protocol lifecycle with real contract names in every step,
  (2) a tabbed architecture map — Conceptual flow / Actual contract topology,
  (3) a conceptual-role ↔ real-contract crosswalk table.

Designed so a reader can build an accurate mental model without ever
needing to open the code. No invented contract names: the actor/target
pills below name only contracts that exist in `contracts/src/`.
"""
from __future__ import annotations

import reflex as rx

from ..components import pill, shell, sidebar_controls
from ..theme import CARD_STYLE, PALETTE


# --------------------------------------------------------------------------- step card
def _step_card(
    number: int,
    title: str,
    actor: str,
    target: str,
    body: str,
    actuarial: str,
) -> rx.Component:
    return rx.box(
        rx.hstack(
            rx.box(
                rx.text(f"{number:02d}",
                        style={"color": PALETTE["bg"],
                               "font_weight": "700",
                               "font_size": "14px"}),
                style={
                    "background":    PALETTE["accent"],
                    "color":         PALETTE["bg"],
                    "padding":       "4px 10px",
                    "border_radius": "6px",
                    "min_width":     "36px",
                    "text_align":    "center",
                },
            ),
            rx.text(title,
                    style={"color": PALETTE["text"], "font_weight": "600",
                           "font_size": "14px"}),
            rx.spacer(),
            rx.hstack(
                pill(actor, "muted"),
                rx.text("→", style={"color": PALETTE["muted"]}),
                pill(target, "good"),
                spacing="2",
                align="center",
            ),
            align="center",
            width="100%",
            margin_bottom="8px",
        ),
        rx.text(
            body,
            style={"color": PALETTE["text"], "font_size": "12px",
                   "line_height": "1.55"},
        ),
        rx.text(
            rx.text.strong("Actuarial meaning: ",
                           style={"color": PALETTE["accent"]}),
            actuarial,
            style={"color": PALETTE["muted"], "font_size": "12px",
                   "line_height": "1.5", "margin_top": "6px"},
        ),
        style={**CARD_STYLE,
               "border_left": f"3px solid {PALETTE['accent']}",
               "margin_bottom": "10px"},
    )


# --------------------------------------------------------------------------- lifecycle
def _lifecycle() -> rx.Component:
    return rx.vstack(
        _step_card(
            1, "Join",
            "Member wallet", "CohortLedger",
            "A wallet is admitted and its cohort (birth-year bucket), "
            "retirement age, sex and salary are recorded in CohortLedger. "
            "Every downstream calculation references this identity.",
            "Establishes the (age x, retirement age r, cohort c) tuple on "
            "which the Gompertz–Makeham life table and the entire EPV "
            "calculation hinge.",
        ),
        _step_card(
            2, "Contribute",
            "Member wallet", "CohortLedger",
            "Each contribution enters the active accumulation pool and mints "
            "non-transferable Pension Investment Units (PIUs) at the current "
            "published price. PIUs are not NFTs, not tradable, and not a "
            "cash-withdrawal right during working life.",
            "Contributions feed EPV(contributions) = Σ vᵗ · ₜpₓ · Cₜ, but "
            "rights are stored in PIU units rather than nominal cash. The "
            "published PIU price is a smoothed NAV / active PIU supply value.",
        ),
        _step_card(
            3, "Fairness check",
            "Governance sandbox", "FairnessGate",
            "Any proposed change to benefit multipliers is submitted to "
            "FairnessGate, which evaluates it against the on-chain baseline. "
            "Failing proposals never reach Timelock.",
            "Corridor rule: max‖ΔMWRᵢ − ΔMWRⱼ‖ / parity ≤ δ. Ensures no "
            "generation is disproportionately worse off than its neighbour "
            "after a reform.",
        ),
        _step_card(
            4, "Retire",
            "Member (at retirement age)", "VestaRouter",
            "At retirement age the member calls VestaRouter. It flips their "
            "status from accumulation to decumulation, burns or locks their "
            "PIU balance, and converts the resulting retirement capital into "
            "an annual pension using the actuarial annuity factor.",
            "The pivot from EPV(contributions) side to EPV(benefits) side. "
            "B_r is computed as retirement capital divided by the annuity "
            "factor, using mortality and discount assumptions from the engine.",
        ),
        _step_card(
            5, "Pool longevity",
            "VestaRouter", "LongevaPool",
            "The retiree's converted capital is deposited into LongevaPool. The "
            "pool survives them: the remainder finances the survivor stream "
            "for the rest of the cohort. MortalityBasisOracle timestamps the "
            "active cohort survival basis, while private experience studies stay off-chain.",
            "Converts accumulation-phase capital into a life annuity priced "
            "off the live survival curve ₜpₓ. Individual longevity risk "
            "becomes pooled cohort risk.",
        ),
        _step_card(
            6, "Attest mortality",
            "Oracle attestation", "MortalityOracle · LongevaPool",
            "When a member dies, an attestation closes their entry. Their "
            "pooled capital remains in LongevaPool to finance surviving "
            "cohort members.",
            "The pool's liability becomes Σ ₜpₓ · Bₜ over the surviving "
            "cohort — individual risk is fully mutualised. The death oracle "
            "and the published mortality basis are deliberately separate: one "
            "confirms deaths, the other proves which aggregate assumption set was active.",
        ),
        _step_card(
            7, "Stream benefits",
            "LongevaPool", "BenefitStreamer → retirees",
            "BenefitStreamer makes periodic payments to each surviving "
            "retiree for life. The benefit stream comes from actuarial "
            "conversion, not from free PIU redemption.",
            "Σ ₜpₓ · Bₜ at each period, discounted at vᵗ = (1+r)⁻ᵗ when "
            "valued — exactly the EPV(benefits) the fairness corridor "
            "defends.",
        ),
        _step_card(
            8, "Stress → backstop",
            "StressOracle", "BackstopVault → CohortLedger",
            "A Monte-Carlo fairness stress publishes worst-case Gini, "
            "intergen index and corridor pass rate to StressOracle. On a "
            "threshold breach, BackstopVault releases reserves into "
            "CohortLedger so promised benefits survive the shock.",
            "One-factor cohort shock: m_c(s) = 1 + β_c·F(s) + ε_c(s). "
            "β is loaded so younger cohorts bear more systemic risk than "
            "retirees — an explicit intergenerational choice.",
        ),
        spacing="2",
        width="100%",
        align="stretch",
    )


# --------------------------------------------------------------------------- maps (tabbed)
_CONCEPTUAL_SVG = r"""
<svg viewBox="0 0 820 340" xmlns="http://www.w3.org/2000/svg"
     preserveAspectRatio="xMidYMid meet"
     style="width:100%;height:auto;background:#0b1220;border-radius:8px">
  <defs>
    <marker id="arr1" viewBox="0 0 10 10" refX="10" refY="5"
            markerWidth="6" markerHeight="6" orient="auto-start-reverse">
      <path d="M 0 0 L 10 5 L 0 10 z" fill="#38bdf8"/>
    </marker>
    <style>
      .n { fill:#111a2e; stroke:#1f2a44; stroke-width:1.2; }
      .n-c { fill:#111a2e; stroke:#38bdf8; stroke-width:1.6; }
      .lbl { fill:#e2e8f0; font:600 12px Inter,system-ui,sans-serif; }
      .sub { fill:#94a3b8; font:400 10px Inter,system-ui,sans-serif; }
      .e { stroke:#38bdf8; stroke-width:1.3; fill:none; marker-end:url(#arr1); }
    </style>
  </defs>

  <rect class="n" x="40"  y="30"  width="170" height="56" rx="10"/>
  <text class="lbl" x="125" y="57" text-anchor="middle">Member</text>
  <text class="sub" x="125" y="74" text-anchor="middle">joins / contributes</text>

  <rect class="n" x="40"  y="140" width="170" height="56" rx="10"/>
  <text class="lbl" x="125" y="167" text-anchor="middle">Governance</text>
  <text class="sub" x="125" y="184" text-anchor="middle">reform proposals</text>

  <rect class="n" x="40"  y="250" width="170" height="56" rx="10"/>
  <text class="lbl" x="125" y="277" text-anchor="middle">Treasury</text>
  <text class="sub" x="125" y="294" text-anchor="middle">backstop reserves</text>

  <rect class="n-c" x="320" y="120" width="180" height="90" rx="12"/>
  <text class="lbl" x="410" y="155" text-anchor="middle">Python engine</text>
  <text class="sub" x="410" y="175" text-anchor="middle">actuarial · fairness</text>
  <text class="sub" x="410" y="190" text-anchor="middle">source of truth</text>

  <rect class="n" x="610" y="30"  width="170" height="56" rx="10"/>
  <text class="lbl" x="695" y="57" text-anchor="middle">Fund promise</text>
  <text class="sub" x="695" y="74" text-anchor="middle">EPV(benefits)</text>

  <rect class="n" x="610" y="140" width="170" height="56" rx="10"/>
  <text class="lbl" x="695" y="167" text-anchor="middle">Fairness corridor</text>
  <text class="sub" x="695" y="184" text-anchor="middle">MWR parity δ</text>

  <rect class="n" x="610" y="250" width="170" height="56" rx="10"/>
  <text class="lbl" x="695" y="277" text-anchor="middle">Resilience</text>
  <text class="sub" x="695" y="294" text-anchor="middle">stress + reserves</text>

  <path class="e" d="M 210 58  C 260 58, 290 140, 320 150"/>
  <path class="e" d="M 210 168 C 260 168, 290 170, 320 170"/>
  <path class="e" d="M 210 278 C 260 278, 290 200, 320 200"/>

  <path class="e" d="M 500 145 C 560 145, 580 58,  610 58"/>
  <path class="e" d="M 500 165 C 560 165, 580 168, 610 168"/>
  <path class="e" d="M 500 190 C 560 190, 580 278, 610 278"/>
</svg>
"""

_TOPOLOGY_SVG = r"""
<svg viewBox="0 0 900 480" xmlns="http://www.w3.org/2000/svg"
     preserveAspectRatio="xMidYMid meet"
     style="width:100%;height:auto;background:#0b1220;border-radius:8px">
  <defs>
    <marker id="arr2" viewBox="0 0 10 10" refX="10" refY="5"
            markerWidth="6" markerHeight="6" orient="auto-start-reverse">
      <path d="M 0 0 L 10 5 L 0 10 z" fill="#38bdf8"/>
    </marker>
    <style>
      .lane { fill:#0e1629; stroke:#1f2a44; stroke-dasharray:3 3; }
      .ltxt { fill:#94a3b8; font:500 11px Inter,system-ui,sans-serif;
              letter-spacing:0.1em; text-transform:uppercase; }
      .n { fill:#111a2e; stroke:#1f2a44; stroke-width:1.2; }
      .n-e { fill:#111a2e; stroke:#38bdf8; stroke-width:1.6; }
      .lbl { fill:#e2e8f0; font:600 12px Inter,system-ui,sans-serif; }
      .sub { fill:#94a3b8; font:400 10px Inter,system-ui,sans-serif; }
      .e { stroke:#38bdf8; stroke-width:1.2; fill:none; marker-end:url(#arr2); }
      .e-dim { stroke:#475569; stroke-width:1; fill:none;
               stroke-dasharray:4 4; }
    </style>
  </defs>

  <!-- Swimlanes -->
  <rect class="lane" x="20"  y="40"  width="240" height="400" rx="10"/>
  <text class="ltxt" x="140" y="62" text-anchor="middle">Actors</text>

  <rect class="lane" x="290" y="40"  width="260" height="400" rx="10"/>
  <text class="ltxt" x="420" y="62" text-anchor="middle">Python engine</text>

  <rect class="lane" x="580" y="40"  width="300" height="400" rx="10"/>
  <text class="ltxt" x="730" y="62" text-anchor="middle">Solidity contracts</text>

  <!-- Actors -->
  <rect class="n" x="50"  y="90"  width="180" height="44" rx="8"/>
  <text class="lbl" x="140" y="116" text-anchor="middle">Member wallet</text>

  <rect class="n" x="50"  y="170" width="180" height="44" rx="8"/>
  <text class="lbl" x="140" y="196" text-anchor="middle">Governance</text>

  <rect class="n" x="50"  y="250" width="180" height="44" rx="8"/>
  <text class="lbl" x="140" y="276" text-anchor="middle">Treasury</text>

  <rect class="n" x="50"  y="330" width="180" height="44" rx="8"/>
  <text class="lbl" x="140" y="356" text-anchor="middle">Mortality attestor</text>

  <!-- Python engine (single node, central) -->
  <rect class="n-e" x="310" y="190" width="220" height="100" rx="12"/>
  <text class="lbl" x="420" y="222" text-anchor="middle">Aequitas engine</text>
  <text class="sub" x="420" y="240" text-anchor="middle">actuarial · fairness · stress</text>
  <text class="sub" x="420" y="258" text-anchor="middle">chain_bridge encoder</text>

  <!-- Contracts -->
  <rect class="n" x="600" y="80"  width="260" height="40" rx="8"/>
  <text class="lbl" x="730" y="104" text-anchor="middle">CohortLedger</text>

  <rect class="n" x="600" y="128" width="260" height="40" rx="8"/>
  <text class="lbl" x="730" y="152" text-anchor="middle">FairnessGate</text>

  <rect class="n" x="600" y="176" width="260" height="40" rx="8"/>
  <text class="lbl" x="730" y="200" text-anchor="middle">VestaRouter</text>

  <rect class="n" x="600" y="224" width="260" height="40" rx="8"/>
  <text class="lbl" x="730" y="248" text-anchor="middle">LongevaPool</text>

  <rect class="n" x="600" y="272" width="260" height="40" rx="8"/>
  <text class="lbl" x="730" y="296" text-anchor="middle">MortalityOracle</text>

  <rect class="n" x="600" y="320" width="260" height="40" rx="8"/>
  <text class="lbl" x="730" y="344" text-anchor="middle">BenefitStreamer</text>

  <rect class="n" x="600" y="368" width="260" height="40" rx="8"/>
  <text class="lbl" x="730" y="392" text-anchor="middle">StressOracle</text>

  <rect class="n" x="600" y="416" width="260" height="24" rx="8"/>
  <text class="lbl" x="730" y="433" text-anchor="middle">BackstopVault</text>

  <!-- Actor → engine -->
  <path class="e" d="M 230 112 C 270 112, 290 220, 310 220"/>
  <path class="e" d="M 230 192 C 270 192, 290 235, 310 235"/>
  <path class="e" d="M 230 272 C 270 272, 290 260, 310 260"/>
  <path class="e" d="M 230 352 C 270 352, 290 275, 310 275"/>

  <!-- Engine → contracts -->
  <path class="e" d="M 530 210 C 560 210, 580 100, 600 100"/>
  <path class="e" d="M 530 220 C 560 220, 580 148, 600 148"/>
  <path class="e" d="M 530 232 C 560 232, 580 196, 600 196"/>
  <path class="e" d="M 530 244 C 560 244, 580 244, 600 244"/>
  <path class="e" d="M 530 256 C 560 256, 580 292, 600 292"/>
  <path class="e" d="M 530 268 C 560 268, 580 340, 600 340"/>
  <path class="e" d="M 530 278 C 560 278, 580 388, 600 388"/>
  <path class="e" d="M 530 288 C 560 288, 580 428, 600 428"/>

  <!-- Telemetry feedback -->
  <path class="e-dim" d="M 600 388 C 560 388, 560 300, 530 280"/>
  <path class="e-dim" d="M 600 100 C 560 100, 560 195, 530 200"/>
</svg>
"""


def _architecture_tabs() -> rx.Component:
    return rx.box(
        rx.text("Architecture map",
                style={"color": PALETTE["text"], "font_weight": "600",
                       "font_size": "14px", "margin_bottom": "4px"}),
        rx.text(
            "Two views of the same system. Start with the conceptual flow "
            "to see who is talking to whom at a high level, then switch to "
            "the topology view to see which real Solidity contract each "
            "piece maps onto.",
            style={"color": PALETTE["muted"], "font_size": "11px",
                   "margin_bottom": "10px"},
        ),
        rx.tabs.root(
            rx.tabs.list(
                rx.tabs.trigger("Conceptual flow", value="concept"),
                rx.tabs.trigger("Actual contract topology", value="topo"),
            ),
            rx.tabs.content(
                rx.html(_CONCEPTUAL_SVG),
                value="concept",
                style={"padding_top": "10px"},
            ),
            rx.tabs.content(
                rx.html(_TOPOLOGY_SVG),
                value="topo",
                style={"padding_top": "10px"},
            ),
            default_value="concept",
            width="100%",
        ),
        style=CARD_STYLE,
    )


# --------------------------------------------------------------------------- crosswalk table
_CROSSWALK = [
    ("Membership + PIU accounting",
     "CohortLedger",
     "registerMember · contribute · setPiuPrice · markRetired"),
    ("Fairness baseline + corridor gate",
     "FairnessGate",
     "setBaseline · submitAndEvaluate"),
    ("Retirement router (accumulation → decumulation)",
     "VestaRouter",
     "openRetirement"),
    ("Longevity pool (lifetime annuity pricing)",
     "LongevaPool",
     "deposit · share accounting"),
    ("Survival curve oracle",
     "MortalityOracle",
     "publishCurve · attestDeath"),
    ("Periodic benefit payout",
     "BenefitStreamer",
     "stream · claim"),
    ("Fairness-stress telemetry",
     "StressOracle",
     "updateStressLevel"),
    ("Reserve vault (stress-gated release)",
     "BackstopVault",
     "deposit · release"),
]


def _crosswalk() -> rx.Component:
    return rx.box(
        rx.text("Conceptual role ↔ real contract",
                style={"color": PALETTE["text"], "font_weight": "600",
                       "font_size": "14px", "margin_bottom": "4px"}),
        rx.text(
            "Every conceptual role in the protocol is implemented by a real "
            "Solidity contract. If a role is missing, no contract is hiding — "
            "that function simply does not exist in the current deployment.",
            style={"color": PALETTE["muted"], "font_size": "11px",
                   "margin_bottom": "10px"},
        ),
        rx.table.root(
            rx.table.header(
                rx.table.row(
                    rx.table.column_header_cell("Conceptual role"),
                    rx.table.column_header_cell("Real contract"),
                    rx.table.column_header_cell("Key functions"),
                ),
            ),
            rx.table.body(
                *[
                    rx.table.row(
                        rx.table.cell(role),
                        rx.table.cell(
                            rx.code(contract,
                                    style={"color": PALETTE["accent"],
                                           "font_size": "12px"}),
                        ),
                        rx.table.cell(
                            rx.code(fns,
                                    style={"color": PALETTE["muted"],
                                           "font_size": "11px"}),
                        ),
                    )
                    for role, contract, fns in _CROSSWALK
                ],
            ),
            width="100%",
        ),
        style=CARD_STYLE,
    )


def _twin_callout() -> rx.Component:
    return rx.box(
        rx.hstack(
            pill("DIGITAL TWIN", "good"),
            rx.text(
                "Want to see the whole lifecycle run through 40 years at "
                "once? Open the Digital Twin — it runs the Python engine "
                "year-by-year and tags every event with the Solidity "
                "contract that would execute it on-chain.",
                style={"color": PALETTE["text"], "font_size": "12px",
                       "line_height": "1.5"},
            ),
            rx.link(
                rx.button("Open twin", color_scheme="cyan", size="1"),
                href="/twin",
            ),
            spacing="3",
            align="center",
        ),
        style={**CARD_STYLE,
               "border_left": f"3px solid {PALETTE['good']}",
               "margin_bottom": "12px"},
    )


def _proof_layer_callout() -> rx.Component:
    return rx.box(
        rx.vstack(
            rx.hstack(
                pill("ACTUARIAL PROOF LAYER", "warn"),
                rx.text(
                    "Python still runs the pension engine in full. The chain is used for methodology versions, parameter snapshots, committed inputs and results, and a small deterministic verifier kernel.",
                    style={"color": PALETTE["text"], "font_size": "12px", "line_height": "1.6"},
                ),
                spacing="3",
                align="center",
                width="100%",
                wrap="wrap",
            ),
            rx.text(
                "What stays off-chain: private member data, mortality fitting, stochastic stress, and full valuation loops. "
                "What goes on-chain: method/version hashes, parameter commitments, result commitments, and bounded spot checks such as MWR and fairness-corridor verification.",
                style={"color": PALETTE["muted"], "font_size": "11px", "line_height": "1.7"},
            ),
            width="100%",
            align="start",
            spacing="2",
        ),
        style={**CARD_STYLE, "border_left": f"3px solid {PALETTE['warn']}", "margin_bottom": "12px"},
    )


def how_page() -> rx.Component:
    return shell(
        "How Aequitas works",
        "A plain-language walkthrough of the protocol in eight steps, a "
        "tabbed architecture map, and a crosswalk that pins every "
        "conceptual role to the real Solidity contract that implements "
        "it. No invented contract names — every pill below refers to a "
        "contract that exists under `contracts/src/`.",
        rx.hstack(
            sidebar_controls(),
            rx.vstack(
                _twin_callout(),
                _proof_layer_callout(),
                _lifecycle(),
                _architecture_tabs(),
                _crosswalk(),
                spacing="3",
                width="100%",
                align="stretch",
            ),
            spacing="3",
            width="100%",
            align="start",
        ),
    )
