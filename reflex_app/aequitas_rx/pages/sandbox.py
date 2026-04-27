"""Sandbox page — deterministic protocol lab and proof surface."""
from __future__ import annotations

import reflex as rx

from ..components import pill, shell, simple_table
from ..components_wallet import confirm_drawer, connect_prompt, protocol_status_banner, wallet_event_bridge
from ..state import AppState
from ..theme import CARD_STYLE, PALETTE, SERIES


def _panel(title: str, *children, subtitle: str = "") -> rx.Component:
    return rx.box(
        rx.text(title, style={"color": PALETTE["text"], "font_weight": "600", "font_size": "15px", "margin_bottom": "4px"}),
        rx.cond(
            subtitle != "",
            rx.text(subtitle, style={"color": PALETTE["muted"], "font_size": "11px", "margin_bottom": "10px"}),
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
        style={"padding": "10px 12px", "border": f"1px solid {PALETTE['edge']}", "border_radius": "10px", "flex": "1 1 140px", "min_width": "140px"},
    )


def _sandbox_controls() -> rx.Component:
    return rx.box(
        rx.heading("Sandbox controls", size="4", style={"color": PALETTE["text"]}),
        rx.text(
            "This is the small deterministic protocol lab. It uses a fixed member set so every valuation, proposal, CPI update, and on-chain proof step can be inspected closely.",
            style={"color": PALETTE["muted"], "font_size": "11px", "margin_top": "6px", "margin_bottom": "12px"},
        ),
        rx.text("Valuation year", style={"color": PALETTE["muted"], "font_size": "11px"}),
        rx.input(value=AppState.valuation_year.to_string(), on_change=AppState.change_valuation_year, type="number", size="1"),
        rx.text("Discount rate", style={"color": PALETTE["muted"], "font_size": "11px", "margin_top": "8px"}),
        rx.input(value=AppState.discount_rate.to_string(), on_change=AppState.change_discount_rate, type="number", step="0.005", size="1"),
        rx.text("Investment return", style={"color": PALETTE["muted"], "font_size": "11px", "margin_top": "8px"}),
        rx.input(value=AppState.investment_return.to_string(), on_change=AppState.change_investment_return, type="number", step="0.005", size="1"),
        rx.text("Salary growth", style={"color": PALETTE["muted"], "font_size": "11px", "margin_top": "8px"}),
        rx.input(value=AppState.salary_growth.to_string(), on_change=AppState.change_salary_growth, type="number", step="0.005", size="1"),
        rx.text("Current CPI index", style={"color": PALETTE["muted"], "font_size": "11px", "margin_top": "8px"}),
        rx.input(value=AppState.current_cpi_index.to_string(), on_change=AppState.change_current_cpi_index, type="number", step="0.1", size="1"),
        rx.text("CPI remains a macro assumption for benefit pressure. PIU price itself is fund-linked: active NAV divided by active PIU supply, then smoothed.", style={"color": PALETTE["muted"], "font_size": "10px"}),
        rx.text("Expected CPI growth", style={"color": PALETTE["muted"], "font_size": "11px", "margin_top": "8px"}),
        rx.input(value=AppState.expected_inflation.to_string(), on_change=AppState.change_expected_inflation, type="number", step="0.005", size="1"),
        rx.text("Used for the deterministic forward path so indexed benefits and liability pressure can be explained before any live action is signed.", style={"color": PALETTE["muted"], "font_size": "10px"}),
        rx.text("Execution-cost preset", style={"color": PALETTE["muted"], "font_size": "11px", "margin_top": "8px"}),
        rx.select(
            ["ethereum", "base", "rollup_low"],
            value=AppState.gas_network_preset,
            on_change=AppState.change_gas_network_preset,
            size="2",
            width="100%",
        ),
        rx.text("This changes the blockchain fee assumption, not the actuarial math. Use it to compare Ethereum-like and L2-style execution economics.", style={"color": PALETTE["muted"], "font_size": "10px"}),
        rx.hstack(
            rx.button("Load sandbox", on_click=AppState.load_demo, color_scheme="cyan", size="2", width="100%"),
            rx.button("Reset", on_click=AppState.reset_demo, variant="soft", color_scheme="gray", size="2", width="100%"),
            spacing="2",
            width="100%",
            margin_top="12px",
        ),
        rx.text(
            "Use this area for deterministic inspection. The Digital Twin is where the full synthetic society evolves at scale.",
            style={"color": PALETTE["muted"], "font_size": "10px", "margin_top": "10px"},
        ),
        style={**CARD_STYLE, "width": "300px", "flex_shrink": "0", "position": "sticky", "top": "92px", "align_self": "start"},
    )


def _sandbox_intro() -> rx.Component:
    return _panel(
        "Small deterministic protocol lab",
        rx.text(
            "The Sandbox is the proof layer. It uses a small fixed scheme so you can inspect the roster, the fund-linked PIU accounting, the fairness state, and the protocol actions closely, then connect the same steps to real verified contracts on Sepolia.",
            style={"color": PALETTE["text"], "font_size": "13px", "line_height": "1.65"},
        ),
        rx.hstack(
            rx.box(
                pill("SIMULATED", "muted"),
                rx.text("Local deterministic state is the explainable source of truth.", style={"color": PALETTE["muted"], "font_size": "11px", "margin_top": "8px"}),
                style={"padding": "10px 12px", "border": f"1px solid {PALETTE['edge']}", "border_radius": "10px", "flex": "1"},
            ),
            rx.box(
                pill("PUBLISHED", "warn"),
                rx.text("Selected outputs can be pushed on-chain from the same proof flow.", style={"color": PALETTE["muted"], "font_size": "11px", "margin_top": "8px"}),
                style={"padding": "10px 12px", "border": f"1px solid {PALETTE['edge']}", "border_radius": "10px", "flex": "1"},
            ),
            rx.box(
                pill("VERIFIED", "good"),
                rx.text("Sepolia addresses and transactions link out to Etherscan.", style={"color": PALETTE["muted"], "font_size": "11px", "margin_top": "8px"}),
                style={"padding": "10px 12px", "border": f"1px solid {PALETTE['edge']}", "border_radius": "10px", "flex": "1"},
            ),
            spacing="3",
            width="100%",
            wrap="wrap",
        ),
        subtitle="This is no longer the main product story. It is the inspection and proof layer that backs up the Twin.",
    )


def _scheme_tab() -> rx.Component:
    return rx.vstack(
        _panel(
            "Fund-linked PIUs in the sandbox",
            rx.text(
                "PIUs are non-transferable pension fund units. Members contribute in cash, the ledger mints PIUs at the published price, and the price is driven by smoothed fund NAV per active PIU supply.",
                style={"color": PALETTE["text"], "font_size": "12px", "line_height": "1.65"},
            ),
            rx.hstack(
                _mini_stat("Current CPI", AppState.current_cpi_fmt, "Macro inflation input"),
                _mini_stat("Current PIU price", AppState.current_piu_price_fmt, "Smoothed active pool unit price"),
                _mini_stat("£1,000 buys", AppState.current_pius_per_1000_fmt, "PIUs minted at the current price"),
                _mini_stat("Expected CPI growth", AppState.expected_inflation_fmt, "Used for the deterministic forward path"),
                spacing="3",
                width="100%",
                wrap="wrap",
                align="stretch",
            ),
            subtitle="This makes the fund-linked unit accounting visible before any on-chain proof step is triggered.",
        ),
        _panel(
            "Deterministic funding path",
            rx.cond(
                AppState.loaded,
                rx.recharts.line_chart(
                    rx.recharts.line(data_key="fund_value_k", name="Assets (£k)", stroke=PALETTE["accent"], stroke_width=2, dot=False),
                    rx.recharts.line(data_key="contributions_k", name="Contributions (£k)", stroke=PALETTE["good"], stroke_width=2, dot=False),
                    rx.recharts.line(data_key="benefit_payments_k", name="Benefits (£k)", stroke=PALETTE["warn"], stroke_width=2, dot=False),
                    rx.recharts.x_axis(data_key="year", stroke=PALETTE["muted"]),
                    rx.recharts.y_axis(stroke=PALETTE["muted"]),
                    rx.recharts.cartesian_grid(stroke=PALETTE["edge"]),
                    rx.recharts.legend(),
                    rx.recharts.graphing_tooltip(),
                    data=AppState.fund_projection_rows,
                    width="100%",
                    height=300,
                ),
                rx.text("Load the sandbox dataset to see the deterministic funding path.", style={"color": PALETTE["muted"]}),
            ),
            subtitle="All series are shown in £k so assets, contributions, and benefits can sit on one honest scale.",
        ),
        rx.hstack(
            _panel(
                "Macro CPI and fund-linked PIU path",
                rx.cond(
                    AppState.fund_projection_rows.length() > 0,
                    rx.recharts.line_chart(
                        rx.recharts.line(data_key="cpi_rebased", name="CPI (base=100)", stroke=PALETTE["accent"], stroke_width=2, dot=False),
                        rx.recharts.line(data_key="piu_price_index", name="PIU price (base=100)", stroke=SERIES[1], stroke_width=2, dot=False),
                        rx.recharts.x_axis(data_key="year", stroke=PALETTE["muted"]),
                        rx.recharts.y_axis(stroke=PALETTE["muted"]),
                        rx.recharts.reference_line(y=100, stroke=PALETTE["muted"], stroke_dasharray="4 4"),
                        rx.recharts.cartesian_grid(stroke=PALETTE["edge"]),
                        rx.recharts.legend(),
                        rx.recharts.graphing_tooltip(),
                        data=AppState.fund_projection_rows,
                        width="100%",
                        height=240,
                    ),
                    rx.text("Load the sandbox dataset to see CPI assumptions and fund-linked PIU pricing.", style={"color": PALETTE["muted"]}),
                ),
                subtitle="Both lines are rebased to 100; CPI is a macro input, while PIU price is fund-linked.",
            ),
            _panel(
                "Outstanding PIUs",
                rx.cond(
                    AppState.fund_projection_rows.length() > 0,
                    rx.recharts.line_chart(
                        rx.recharts.line(data_key="total_pius_k", name="Outstanding PIUs (k)", stroke=PALETTE["good"], stroke_width=2, dot=False),
                        rx.recharts.x_axis(data_key="year", stroke=PALETTE["muted"]),
                        rx.recharts.y_axis(stroke=PALETTE["muted"]),
                        rx.recharts.cartesian_grid(stroke=PALETTE["edge"]),
                        rx.recharts.graphing_tooltip(),
                        data=AppState.fund_projection_rows,
                        width="100%",
                        height=240,
                    ),
                    rx.text("Load the sandbox dataset to see outstanding PIUs.", style={"color": PALETTE["muted"]}),
                ),
                subtitle="This is the running stock of pension units that later converts into indexed pension flows.",
            ),
            spacing="3",
            width="100%",
            align="stretch",
        ),
        rx.hstack(
            _panel(
                "Cohort composition",
                rx.cond(
                    AppState.cohort_contrib_rows.length() > 0,
                    rx.recharts.bar_chart(
                        rx.recharts.bar(data_key="total_contributions", name="Total contributions", fill=PALETTE["accent"]),
                        rx.recharts.x_axis(data_key="cohort", stroke=PALETTE["muted"]),
                        rx.recharts.y_axis(stroke=PALETTE["muted"]),
                        rx.recharts.cartesian_grid(stroke=PALETTE["edge"]),
                        rx.recharts.graphing_tooltip(),
                        data=AppState.cohort_contrib_rows,
                        width="100%",
                        height=240,
                    ),
                    rx.text("Load the sandbox dataset to see cohort composition.", style={"color": PALETTE["muted"]}),
                ),
                subtitle="Who is carrying the contribution base in the small deterministic scheme.",
            ),
            _panel(
                "Latest sandbox operations",
                rx.cond(
                    AppState.event_rows.length() > 0,
                    simple_table([("seq", "#"), ("event", "Event"), ("hash", "Hash")], AppState.event_rows),
                    rx.text("No sandbox events recorded yet.", style={"color": PALETTE["muted"]}),
                ),
                subtitle="The sandbox keeps an inspectable audit trail even before anything is signed on-chain.",
            ),
            spacing="3",
            width="100%",
            align="stretch",
        ),
        width="100%",
        spacing="0",
    )


def _members_tab() -> rx.Component:
    return rx.vstack(
        _panel(
            "Member roster",
            rx.cond(
                AppState.loaded,
                simple_table(
                    [
                        ("wallet", "Wallet"),
                        ("cohort", "Cohort"),
                        ("age", "Age"),
                        ("salary", "Salary"),
                        ("contribution_rate", "Contrib rate"),
                        ("retirement_age", "Retire age"),
                        ("total_contributions", "Contrib total"),
                        ("piu_balance", "PIU balance"),
                        ("piu_value", "PIU value"),
                        ("piu_price", "PIU price"),
                    ],
                    AppState.member_rows,
                ),
                rx.text("Load the sandbox dataset to populate the roster.", style={"color": PALETTE["muted"]}),
            ),
            subtitle="Every member in the sandbox is inspectable. This is the small deterministic contrast to the Twin's large synthetic society.",
        ),
        _panel(
            "Per-member actuarial valuation",
            rx.cond(
                AppState.loaded,
                simple_table(
                    [
                        ("wallet", "Wallet"),
                        ("epv_contributions", "EPV contrib"),
                        ("epv_benefits", "EPV benefit"),
                        ("money_worth_ratio", "MWR"),
                        ("current_piu_price", "Current PIU price"),
                        ("current_piu_value", "Current PIU value"),
                        ("projected_annual_benefit_piu", "Pension units"),
                        ("projected_annual_benefit", "Indexed pension"),
                        ("replacement_ratio", "Replacement"),
                    ],
                    AppState.valuation_rows,
                ),
                rx.text("Load the sandbox dataset to see the valuation table.", style={"color": PALETTE["muted"]}),
            ),
            subtitle="This is where the proof layer shows the individual actuarial quantities behind the cohort story.",
        ),
        _panel(
            "Deterministic member drill-down",
            rx.cond(
                AppState.loaded,
                rx.vstack(
                    rx.hstack(
                        rx.foreach(
                            AppState.member_rows,
                            lambda row: rx.box(
                                row["wallet"],
                                on_click=AppState.select_wallet(row["wallet"]),
                                style={
                                    "padding": "4px 10px",
                                    "border_radius": "999px",
                                    "border": rx.cond(AppState.selected_wallet == row["wallet"], f"1px solid {PALETTE['accent']}", f"1px solid {PALETTE['edge']}"),
                                    "background": rx.cond(AppState.selected_wallet == row["wallet"], PALETTE["bg"], PALETTE["panel"]),
                                    "color": rx.cond(AppState.selected_wallet == row["wallet"], PALETTE["accent"], PALETTE["muted"]),
                                    "font_size": "11px",
                                    "cursor": "pointer",
                                    "_hover": {"border_color": PALETTE["accent"]},
                                },
                            ),
                        ),
                        spacing="2",
                        wrap="wrap",
                        width="100%",
                    ),
                    rx.recharts.line_chart(
                        rx.recharts.line(data_key="nominal_piu_value_k", name="Indexed pension value (£k)", stroke=PALETTE["accent"], stroke_width=2, dot=False),
                        rx.recharts.line(data_key="contribution_k", name="Contribution (£k)", stroke=PALETTE["good"], stroke_width=2, dot=False),
                        rx.recharts.line(data_key="benefit_payment_k", name="Benefit payment (£k)", stroke=PALETTE["warn"], stroke_width=2, dot=False),
                        rx.recharts.x_axis(data_key="year", stroke=PALETTE["muted"]),
                        rx.recharts.y_axis(stroke=PALETTE["muted"]),
                        rx.recharts.cartesian_grid(stroke=PALETTE["edge"]),
                        rx.recharts.legend(),
                        rx.recharts.graphing_tooltip(),
                        data=AppState.member_projection_rows,
                        width="100%",
                        height=280,
                    ),
                    rx.recharts.line_chart(
                        rx.recharts.line(data_key="piu_balance_k", name="Accumulated PIUs (k)", stroke=SERIES[1], stroke_width=2, dot=False),
                        rx.recharts.line(data_key="benefit_piu_k", name="Pension units (k)", stroke=PALETTE["warn"], stroke_width=2, dot=False),
                        rx.recharts.x_axis(data_key="year", stroke=PALETTE["muted"]),
                        rx.recharts.y_axis(stroke=PALETTE["muted"]),
                        rx.recharts.cartesian_grid(stroke=PALETTE["edge"]),
                        rx.recharts.legend(),
                        rx.recharts.graphing_tooltip(),
                        data=AppState.member_projection_rows,
                        width="100%",
                        height=220,
                    ),
                    rx.recharts.line_chart(
                        rx.recharts.line(data_key="cpi_rebased", name="CPI (base=100)", stroke=PALETTE["accent"], stroke_width=2, dot=False),
                        rx.recharts.line(data_key="piu_price_index", name="PIU price (base=100)", stroke=PALETTE["good"], stroke_width=2, dot=False),
                        rx.recharts.x_axis(data_key="year", stroke=PALETTE["muted"]),
                        rx.recharts.y_axis(stroke=PALETTE["muted"]),
                        rx.recharts.reference_line(y=100, stroke=PALETTE["muted"], stroke_dasharray="4 4"),
                        rx.recharts.cartesian_grid(stroke=PALETTE["edge"]),
                        rx.recharts.legend(),
                        rx.recharts.graphing_tooltip(),
                        data=AppState.member_projection_rows,
                        width="100%",
                        height=220,
                    ),
                    spacing="3",
                    width="100%",
                ),
                rx.text("Load the sandbox dataset to inspect a member lifecycle.", style={"color": PALETTE["muted"]}),
            ),
            subtitle="A small proof scheme lets you inspect one member all the way through accumulation and retirement assumptions.",
        ),
        width="100%",
        spacing="0",
    )


def _fairness_tab() -> rx.Component:
    return rx.vstack(
        _panel(
            "Deterministic cohort fairness",
            rx.cond(
                AppState.cohorts_count >= 2,
                rx.recharts.bar_chart(
                    rx.recharts.bar(data_key="mwr", name="MWR", fill=PALETTE["accent"]),
                    rx.recharts.x_axis(data_key="cohort", stroke=PALETTE["muted"]),
                    rx.recharts.y_axis(stroke=PALETTE["muted"]),
                    rx.recharts.reference_line(y=1, stroke=PALETTE["muted"], stroke_dasharray="4 4"),
                    rx.recharts.cartesian_grid(stroke=PALETTE["edge"]),
                    rx.recharts.graphing_tooltip(),
                    data=AppState.cohort_mwr_rows,
                    width="100%",
                    height=260,
                ),
                rx.text("Load at least two cohorts to inspect sandbox fairness.", style={"color": PALETTE["muted"]}),
            ),
            subtitle="The sandbox shows the current deterministic fairness state before any stochastic stress is added.",
        ),
        _panel(
            "Proposal before / after",
            rx.cond(
                AppState.cohorts_count >= 2,
                rx.vstack(
                    rx.hstack(
                        rx.foreach(
                            AppState.cohort_mwr_rows,
                            lambda row: rx.vstack(
                                rx.text(row["cohort"].to_string(), style={"color": PALETTE["muted"], "font_size": "11px"}),
                                rx.input(
                                    default_value="1.00",
                                    on_change=lambda v: AppState.set_multiplier(row["cohort"].to_string(), v),
                                    type="number",
                                    step="0.01",
                                    size="1",
                                    width="80px",
                                ),
                                spacing="1",
                                align="center",
                            ),
                        ),
                        spacing="2",
                        wrap="wrap",
                        width="100%",
                    ),
                    rx.hstack(
                        rx.text("Corridor δ (%)", style={"color": PALETTE["muted"], "font_size": "11px"}),
                        rx.input(value=AppState.corridor_delta_pct.to_string(), on_change=AppState.set_corridor_delta, type="number", step=1, size="1", width="80px"),
                        rx.button("Evaluate locally", on_click=AppState.evaluate_sandbox_proposal, color_scheme="cyan", size="2"),
                        spacing="3",
                        align="center",
                    ),
                    rx.cond(
                        AppState.sandbox_ran,
                        rx.vstack(
                            rx.hstack(
                                rx.cond(AppState.sandbox_is_pass, pill("LOCAL PASS", "good"), pill("LOCAL FAIL", "bad")),
                                rx.text(AppState.sandbox_verdict, style={"color": PALETTE["text"], "font_size": "12px"}),
                                spacing="2",
                                align="center",
                            ),
                            simple_table(
                                [("cohort", "Cohort"), ("mwr_before", "MWR before"), ("mwr_after", "MWR after")],
                                AppState.sandbox_comparison_rows,
                            ),
                            spacing="2",
                            width="100%",
                        ),
                        rx.text("No local proposal has been evaluated yet.", style={"color": PALETTE["muted"]}),
                    ),
                    spacing="3",
                    width="100%",
                ),
                rx.text("Load the sandbox dataset and create at least two cohorts first.", style={"color": PALETTE["muted"]}),
            ),
            subtitle="This is the deterministic proof before the same proposal is pushed through a live Sepolia action.",
        ),
        _panel(
            "Mortality learning in the sandbox",
            rx.text(
                "The Sandbox keeps mortality learning inspectable. It starts from the baseline Gompertz prior, compares that prior with a deterministic cohort experience study, and shows how much weight the protocol would currently give to fund-specific experience.",
                style={"color": PALETTE["text"], "font_size": "12px", "line_height": "1.65"},
            ),
            rx.hstack(
                rx.foreach(
                    AppState.sandbox_mortality_summary_rows,
                    lambda row: _mini_stat(row["label"], row["value"], "Compact, publishable basis metadata"),
                ),
                spacing="3",
                width="100%",
                wrap="wrap",
                align="stretch",
            ),
            rx.cond(
                AppState.sandbox_mortality_rows.length() > 0,
                simple_table(
                    [
                        ("cohort", "Cohort"),
                        ("exposure_years", "Exposure"),
                        ("observed_deaths", "Observed"),
                        ("expected_deaths", "Expected"),
                        ("observed_expected", "O/E"),
                        ("credibility_pct", "Credibility %"),
                        ("blended_multiplier", "Basis multiplier"),
                        ("stable_enough", "Status"),
                    ],
                    AppState.sandbox_mortality_rows,
                ),
                rx.text("Load the sandbox dataset to inspect the mortality study.", style={"color": PALETTE["muted"]}),
            ),
            subtitle="This is still privacy-preserving. The Sandbox exposes cohort totals and the publishable basis snapshot, not raw death records.",
        ),
        width="100%",
        spacing="0",
    )


def _proof_step_card(row) -> rx.Component:
    live_kind = rx.cond(row["is_live"] == "yes", "good", "muted")
    status_kind = rx.cond(
        row["status"] == "CONFIRMED",
        "good",
        rx.cond(
            row["status"] == "PENDING",
            "warn",
            rx.cond(
                (row["status"] == "LOCAL PASS") | (row["status"] == "READY") | (row["status"] == "LOCAL READY"),
                "good",
                rx.cond(
                    row["status"] == "LOCAL FAIL",
                    "bad",
                    "muted",
                ),
            ),
        ),
    )
    return rx.box(
        rx.hstack(
            rx.vstack(
                rx.hstack(
                    rx.text(row["title"], style={"color": PALETTE["text"], "font_weight": "700", "font_size": "13px"}),
                    pill(row["live_label"], live_kind),
                    pill(row["status"], status_kind),
                    spacing="2",
                    align="center",
                    wrap="wrap",
                ),
                rx.text(row["summary"], style={"color": PALETTE["text"], "font_size": "12px", "line_height": "1.6"}),
                rx.text("Maps to ", row["contract_function"], style={"color": PALETTE["muted"], "font_size": "11px"}),
                rx.text(row["evidence"], style={"color": PALETTE["muted"], "font_size": "11px"}),
                rx.text(row["before_after"], style={"color": PALETTE["muted"], "font_size": "11px"}),
                rx.text(
                    "Estimated model cost: ",
                    row["estimated_cost_label"],
                    " · ",
                    row["estimated_gas_label"],
                    " · counted transactions: ",
                    row["count_label"],
                    style={"color": PALETTE["muted"], "font_size": "11px"},
                ),
                rx.text(
                    "Actual signed cost: ",
                    row["actual_cost_label"],
                    " · ",
                    row["actual_gas_label"],
                    style={"color": PALETTE["muted"], "font_size": "11px"},
                ),
                rx.text(row["cost_note"], style={"color": PALETTE["muted"], "font_size": "10px", "line_height": "1.5"}),
                spacing="1",
                align="start",
            ),
            rx.spacer(),
            rx.vstack(
                rx.cond(
                    row["contract_url"] != "",
                    rx.link("View contract ↗", href=row["contract_url"], is_external=True, style={"color": PALETTE["accent"], "font_size": "11px"}),
                    rx.text("No contract link", style={"color": PALETTE["muted"], "font_size": "11px"}),
                ),
                rx.cond(
                    row["tx_url"] != "",
                    rx.link(row["latest_tx_short"], href=row["tx_url"], is_external=True, style={"color": PALETTE["accent"], "font_size": "11px"}),
                    rx.text("No tx yet", style={"color": PALETTE["muted"], "font_size": "11px"}),
                ),
                rx.cond(
                    row["key"] == "demo_members",
                    rx.button("Load sandbox", on_click=AppState.load_demo, size="1", color_scheme="cyan", variant="soft"),
                    rx.cond(
                        row["is_live"] == "yes",
                        rx.button("Open action", on_click=AppState.open_action(row["key"]), size="1", color_scheme="cyan", variant="soft"),
                        rx.fragment(),
                    ),
                ),
                spacing="2",
                align="end",
            ),
            width="100%",
            align="start",
        ),
        style={"padding": "12px 14px", "border": f"1px solid {PALETTE['edge']}", "border_radius": "12px", "background": "rgba(15, 23, 42, 0.45)"},
    )


def _proof_tab() -> rx.Component:
    return rx.vstack(
        connect_prompt(),
        _panel(
            "Execution cost of the proof flow",
            rx.text(
                AppState.sandbox_gas_summary_text,
                style={"color": PALETTE["text"], "font_size": "12px", "line_height": "1.65"},
            ),
            rx.hstack(
                _mini_stat("Fee preset", AppState.gas_network_label, "Selected network assumption"),
                _mini_stat("Modelled proof cost", AppState.sandbox_gas_total_fmt, "If the whole proof flow were executed on-chain"),
                _mini_stat("Actual signed fees", AppState.actual_fee_total_fmt, "Confirmed wallet-signed fees so far"),
                _mini_stat("Cumulative gas", AppState.sandbox_gas_total_gas_units.to_string(), "Estimated gas units across the deterministic flow"),
                spacing="3",
                width="100%",
                wrap="wrap",
                align="stretch",
            ),
            rx.cond(
                AppState.sandbox_gas_comparison_rows.length() > 0,
                rx.recharts.bar_chart(
                    rx.recharts.bar(data_key="total_cost_k", name="Total cost (£k)", fill=PALETTE["accent"]),
                    rx.recharts.x_axis(data_key="preset_label", stroke=PALETTE["muted"]),
                    rx.recharts.y_axis(stroke=PALETTE["muted"]),
                    rx.recharts.cartesian_grid(stroke=PALETTE["edge"]),
                    rx.recharts.graphing_tooltip(),
                    data=AppState.sandbox_gas_comparison_rows,
                    width="100%",
                    height=240,
                ),
                rx.fragment(),
            ),
            subtitle="Estimated model cost and actual signed fees are kept separate on purpose.",
        ),
        _panel(
            "On-chain verifiable sandbox flow",
            rx.text(
                "These are the deterministic sandbox steps the jury can inspect locally and, where supported, verify on Sepolia. Plain-English meaning comes first; contracts and Etherscan links are secondary proof.",
                style={"color": PALETTE["text"], "font_size": "12px", "line_height": "1.6", "margin_bottom": "10px"},
            ),
            rx.box(
                rx.text(
                    "For mortality learning, the chain only needs the published basis version, cohort digest, credibility score, and study hash. Raw death records, exposure files, and model fitting stay off-chain.",
                    style={"color": PALETTE["muted"], "font_size": "11px", "line_height": "1.65"},
                ),
                style={"padding": "10px 12px", "border": f"1px solid {PALETTE['edge']}", "border_radius": "10px", "margin_bottom": "10px"},
            ),
            rx.vstack(
                rx.foreach(AppState.sandbox_action_rows, _proof_step_card),
                spacing="3",
                width="100%",
            ),
        ),
        _panel(
            "Recent proof transactions",
            rx.cond(
                AppState.sandbox_recent_tx_rows.length() > 0,
                simple_table(
                    [("action", "Action"), ("short_hash", "Latest tx"), ("fee_label", "Actual fee"), ("status", "Status")],
                    AppState.sandbox_recent_tx_rows,
                ),
                rx.text("No live sandbox transaction has been sent from this UI session yet.", style={"color": PALETTE["muted"]}),
            ),
            subtitle="When you sign a sandbox action, it shows up here with an Etherscan link inside the step card above.",
        ),
        _panel(
            "Technical appendix",
            rx.accordion.root(
                rx.accordion.item(
                    header=rx.text("Preview bridged payloads", style={"color": PALETTE["muted"], "font_size": "11px"}),
                    content=rx.vstack(
                        rx.text("Baseline payload", style={"color": PALETTE["text"], "font_size": "12px"}),
                        rx.code_block(AppState.baseline_payload.to_string(), language="json", show_line_numbers=False, width="100%"),
                        rx.text("Proposal payload", style={"color": PALETTE["text"], "font_size": "12px", "margin_top": "8px"}),
                        rx.code_block(AppState.proposal_payload.to_string(), language="json", show_line_numbers=False, width="100%"),
                        rx.text("PIU price payload", style={"color": PALETTE["text"], "font_size": "12px", "margin_top": "8px"}),
                        rx.code_block(AppState.piu_price_payload.to_string(), language="json", show_line_numbers=False, width="100%"),
                        rx.text("Mortality basis payload", style={"color": PALETTE["text"], "font_size": "12px", "margin_top": "8px"}),
                        rx.code_block(AppState.mortality_basis_payload.to_string(), language="json", show_line_numbers=False, width="100%"),
                        spacing="2",
                        width="100%",
                    ),
                    value="payloads",
                ),
                type="single",
                collapsible=True,
                width="100%",
            ),
            subtitle="Advanced details are still available, but they no longer dominate the proof story.",
        ),
        width="100%",
        spacing="0",
    )


def _sepolia_proof_tab() -> rx.Component:
    """Sepolia proof demo — Phase 1 UI.

    Each Sandbox member has a real Sepolia address so the jury can inspect
    registration, contributions, PIU minting, retirement conversion,
    governance proposals, and investment votes on Etherscan.
    """
    intro = _panel(
        "Sepolia proof demo",
        rx.text(
            "Digital Twin members are simulated at scale. "
            "Sandbox members are a small deterministic Sepolia demo set. "
            "Each Sandbox member has a real testnet address so the jury can "
            "inspect registration, contributions, PIUs minted, retirement "
            "conversion, fairness proposals, and investment votes on Etherscan.",
            style={"color": PALETTE["text"], "font_size": "13px", "line_height": "1.65"},
        ),
        rx.box(
            rx.text(
                "These are Sepolia demo wallets only. They are not production "
                "custody wallets and contain no real member assets.",
                style={"color": PALETTE["warn"], "font_size": "12px", "line_height": "1.55"},
            ),
            style={
                "padding": "10px 12px",
                "border": f"1px solid {PALETTE['edge']}",
                "border_radius": "10px",
                "margin_top": "10px",
                "background": "rgba(234, 179, 8, 0.06)",
            },
        ),
        subtitle="This panel is gated by AEQUITAS_DEVTOOLS=1.",
    )

    mode_panel = _panel(
        "Broadcast mode",
        rx.hstack(
            rx.select(
                ["Dry run", "Live Sepolia broadcast"],
                value=rx.cond(
                    AppState.sandbox_sepolia_live_mode,
                    "Live Sepolia broadcast",
                    "Dry run",
                ),
                on_change=AppState.set_sandbox_live_mode,
                size="2",
            ),
            rx.cond(
                AppState.sandbox_sepolia_live_mode,
                rx.cond(
                    AppState.sandbox_sepolia_live_armed,
                    rx.hstack(
                        pill("LIVE ARMED", "warn"),
                        rx.button("Disarm", on_click=AppState.disarm_live_broadcast,
                                  size="1", variant="soft", color_scheme="gray"),
                        spacing="2", align="center",
                    ),
                    rx.button(
                        "Confirm: arm Live Sepolia broadcast",
                        on_click=AppState.arm_live_broadcast,
                        color_scheme="red", size="2",
                    ),
                ),
                pill("DRY RUN", "muted"),
            ),
            rx.button("Start new demo run",
                      on_click=AppState.start_new_sandbox_run,
                      size="1", variant="soft", color_scheme="gray"),
            spacing="3", align="center", wrap="wrap",
        ),
        rx.cond(
            AppState.sandbox_sepolia_live_mode,
            rx.box(
                rx.text(
                    "Live Sepolia broadcast will spend Sepolia ETH and submit "
                    "real testnet transactions using the configured demo keys.",
                    style={"color": PALETTE["warn"], "font_size": "12px", "line_height": "1.55"},
                ),
                style={
                    "padding": "10px 12px",
                    "border": f"1px solid {PALETTE['edge']}",
                    "border_radius": "10px", "margin_top": "10px",
                    "background": "rgba(234, 179, 8, 0.06)",
                },
            ),
            rx.fragment(),
        ),
        rx.cond(
            AppState.sandbox_sepolia_idempotency_warning != "",
            rx.text(
                AppState.sandbox_sepolia_idempotency_warning,
                style={"color": PALETTE["warn"], "font_size": "11px", "margin_top": "8px"},
            ),
            rx.fragment(),
        ),
        rx.cond(
            AppState.sandbox_sepolia_precheck_errors.length() > 0,
            rx.vstack(
                rx.foreach(
                    AppState.sandbox_sepolia_precheck_errors,
                    lambda err: rx.text(
                        "• ", err,
                        style={"color": PALETTE["bad"], "font_size": "11px"},
                    ),
                ),
                spacing="1", align="start", margin_top="8px",
            ),
            rx.fragment(),
        ),
        subtitle="Dry run is the default and never sends a transaction. Live mode requires explicit confirmation.",
    )

    funding_panel = _panel(
        "Fund sandbox wallets",
        rx.text(
            "Member wallet ETH pays for gas on member-signed votes. "
            "Protocol pool funding pays for pension benefits. "
            "Funding is independent of the demo broadcast arm.",
            style={"color": PALETTE["muted"], "font_size": "11px", "margin_bottom": "10px"},
        ),
        rx.cond(
            AppState.sandbox_sepolia_live_mode,
            rx.cond(
                AppState.sandbox_sepolia_funding_armed,
                rx.hstack(
                    rx.button("Fund sandbox wallets",
                              on_click=AppState.fund_sandbox_wallets,
                              color_scheme="cyan", size="2"),
                    rx.button("Disarm funding", on_click=AppState.disarm_funding_broadcast,
                              size="1", variant="soft", color_scheme="gray"),
                    rx.text(
                        AppState.sandbox_sepolia_funding_status,
                        style={"color": PALETTE["muted"], "font_size": "11px"},
                    ),
                    spacing="3", align="center", wrap="wrap",
                ),
                rx.hstack(
                    rx.button(
                        "Arm wallet funding (spends Sepolia ETH)",
                        on_click=AppState.arm_funding_broadcast,
                        color_scheme="orange", size="2",
                    ),
                    rx.text(
                        "Tops up member gas wallets from DEPLOYER_PK. "
                        "Already-funded wallets are skipped.",
                        style={"color": PALETTE["muted"], "font_size": "11px"},
                    ),
                    spacing="3", align="center", wrap="wrap",
                ),
            ),
            rx.text(
                "Switch to Live Sepolia broadcast mode to fund sandbox wallets.",
                style={"color": PALETTE["muted"], "font_size": "11px"},
            ),
        ),
        rx.cond(
            AppState.sandbox_sepolia_funding_rows.length() > 0,
            simple_table(
                [
                    ("label", "Member"),
                    ("balance_before_eth", "Balance before (ETH)"),
                    ("balance_after_eth", "Balance after (ETH)"),
                    ("status", "Status"),
                ],
                AppState.sandbox_sepolia_funding_rows,
            ),
            rx.fragment(),
        ),
        subtitle="Funding only runs when live mode is armed. Dry run never sends ETH.",
    )

    env_panel = _panel(
        "Environment & registry",
        rx.cond(
            AppState.sandbox_sepolia_env_ok,
            rx.text("Env OK: SEPOLIA_RPC_URL, DEPLOYER_PK, cast detected.",
                    style={"color": PALETTE["good"], "font_size": "12px"}),
            rx.text(
                rx.cond(
                    AppState.sandbox_sepolia_env_error != "",
                    AppState.sandbox_sepolia_env_error,
                    "Set SEPOLIA_RPC_URL, DEPLOYER_PK in .env and ensure foundry's `cast` is on PATH.",
                ),
                style={"color": PALETTE["warn"], "font_size": "12px"},
            ),
        ),
        rx.text(
            AppState.sandbox_sepolia_registry_message,
            style={"color": PALETTE["muted"], "font_size": "11px", "margin_top": "6px"},
        ),
        rx.text(
            "Sandbox wallets loaded: ",
            AppState.sandbox_sepolia_wallets_loaded.to_string(),
            style={"color": PALETTE["muted"], "font_size": "11px", "margin_top": "6px"},
        ),
    )

    buttons = _panel(
        "Run the Sepolia proof demo",
        rx.hstack(
            rx.button("Generate / load sandbox wallets",
                      on_click=AppState.sandbox_generate_wallets, color_scheme="cyan", size="2"),
            rx.button("Run full Sandbox Sepolia proof demo",
                      on_click=AppState.run_full_sandbox_sepolia_demo, color_scheme="cyan", size="2"),
            spacing="2", wrap="wrap",
        ),
        rx.hstack(
            rx.button("Register sandbox members",
                      on_click=lambda: AppState.sandbox_run_sepolia_step("register_members"),
                      variant="soft", color_scheme="cyan", size="1"),
            rx.button("Publish sandbox PIU price",
                      on_click=lambda: AppState.sandbox_run_sepolia_step("publish_piu_price"),
                      variant="soft", color_scheme="cyan", size="1"),
            rx.button("Post sandbox contributions",
                      on_click=lambda: AppState.sandbox_run_sepolia_step("post_contributions"),
                      variant="soft", color_scheme="cyan", size="1"),
            rx.button("Open one retirement",
                      on_click=lambda: AppState.sandbox_run_sepolia_step("open_retirement"),
                      variant="soft", color_scheme="cyan", size="1"),
            spacing="2", wrap="wrap", margin_top="8px",
        ),
        rx.hstack(
            rx.button("Submit fairness proposal PASS",
                      on_click=lambda: AppState.sandbox_run_sepolia_step("fairness_proposal_pass"),
                      variant="soft", color_scheme="green", size="1"),
            rx.button("Submit fairness proposal FAIL",
                      on_click=lambda: AppState.sandbox_run_sepolia_step("fairness_proposal_fail"),
                      variant="soft", color_scheme="red", size="1"),
            spacing="2", wrap="wrap", margin_top="8px",
        ),
        rx.hstack(
            rx.button("Create investment ballot",
                      on_click=lambda: AppState.sandbox_run_sepolia_step("ballot_create"),
                      variant="soft", color_scheme="cyan", size="1"),
            rx.button("Publish ballot voting weights",
                      on_click=lambda: AppState.sandbox_run_sepolia_step("ballot_weights"),
                      variant="soft", color_scheme="cyan", size="1"),
            rx.button("Cast sandbox investment votes",
                      on_click=lambda: AppState.sandbox_run_sepolia_step("ballot_votes"),
                      variant="soft", color_scheme="cyan", size="1"),
            rx.button("Finalize investment policy",
                      on_click=lambda: AppState.sandbox_run_sepolia_step("ballot_finalize"),
                      variant="soft", color_scheme="cyan", size="1"),
            spacing="2", wrap="wrap", margin_top="8px",
        ),
        rx.hstack(
            rx.button("Publish actuarial proof bundle",
                      on_click=lambda: AppState.sandbox_run_sepolia_step("actuarial_publish"),
                      variant="soft", color_scheme="purple", size="1"),
            spacing="2", wrap="wrap", margin_top="8px",
        ),
        rx.text(
            AppState.sandbox_sepolia_message,
            style={"color": PALETTE["muted"], "font_size": "11px", "margin_top": "10px"},
        ),
        subtitle="Repeated demo runs may skip steps already recorded on-chain. Use 'Start new demo run' to reset the UI.",
    )

    roster = _panel(
        "Sandbox member roster",
        rx.cond(
            AppState.sandbox_sepolia_member_rows.length() > 0,
            rx.vstack(
                rx.foreach(
                    AppState.sandbox_sepolia_member_rows,
                    lambda row: rx.box(
                        rx.hstack(
                            rx.vstack(
                                rx.text(row["label"], style={"color": PALETTE["text"], "font_weight": "600", "font_size": "12px"}),
                                rx.text("Cohort ", row["cohort"].to_string(), " · age ", row["age"].to_string(),
                                        style={"color": PALETTE["muted"], "font_size": "11px"}),
                                rx.link(row["address_short"], href=row["address_url"], is_external=True,
                                        style={"color": PALETTE["accent"], "font_size": "11px"}),
                                spacing="1", align="start",
                            ),
                            rx.spacer(),
                            rx.vstack(
                                rx.cond(row["registered_url"] != "",
                                        rx.link("registered ↗", href=row["registered_url"], is_external=True,
                                                style={"color": PALETTE["accent"], "font_size": "11px"}),
                                        rx.text("registered: —", style={"color": PALETTE["muted"], "font_size": "11px"})),
                                rx.cond(row["contribution_url"] != "",
                                        rx.link("contribution ↗", href=row["contribution_url"], is_external=True,
                                                style={"color": PALETTE["accent"], "font_size": "11px"}),
                                        rx.text("contribution: —", style={"color": PALETTE["muted"], "font_size": "11px"})),
                                rx.cond(row["retirement_url"] != "",
                                        rx.link("retirement ↗", href=row["retirement_url"], is_external=True,
                                                style={"color": PALETTE["accent"], "font_size": "11px"}),
                                        rx.text("retirement: —", style={"color": PALETTE["muted"], "font_size": "11px"})),
                                rx.cond(row["vote_url"] != "",
                                        rx.link("investment vote ↗", href=row["vote_url"], is_external=True,
                                                style={"color": PALETTE["accent"], "font_size": "11px"}),
                                        rx.text("investment vote: —", style={"color": PALETTE["muted"], "font_size": "11px"})),
                                spacing="1", align="end",
                            ),
                            width="100%", align="start",
                        ),
                        style={"padding": "10px 12px", "border": f"1px solid {PALETTE['edge']}", "border_radius": "10px"},
                    ),
                ),
                spacing="2", width="100%",
            ),
            rx.text("No sandbox wallets yet. Click Generate / load sandbox wallets.",
                    style={"color": PALETTE["muted"]}),
        ),
        subtitle="Each Sandbox member has a real Sepolia address; private keys are stored locally and never displayed.",
    )

    steps = _panel(
        "Protocol proof steps",
        rx.cond(
            AppState.sandbox_sepolia_step_rows.length() > 0,
            simple_table(
                [
                    ("step", "#"),
                    ("label", "Step"),
                    ("contract", "Contract"),
                    ("function", "Function"),
                    ("actor", "Actor"),
                    ("member_wallet", "Member"),
                    ("short_hash", "Tx"),
                    ("status", "Status"),
                ],
                AppState.sandbox_sepolia_step_rows,
            ),
            rx.text("No steps yet.", style={"color": PALETTE["muted"]}),
        ),
        subtitle="Operator-signed: register, contribute, setPiuPrice, openRetirement, fairness, ballot create/weights/finalize. Member-signed: castVote.",
    )

    story = _panel(
        "Open Etherscan story",
        rx.cond(
            AppState.sandbox_sepolia_story_rows.length() > 0,
            rx.vstack(
                rx.foreach(
                    AppState.sandbox_sepolia_story_rows,
                    lambda row: rx.cond(
                        row["row_type"] == "header",
                        rx.text(
                            row["title"],
                            style={
                                "color": PALETTE["text"], "font_weight": "600",
                                "font_size": "12px", "margin_top": "8px",
                                "padding_bottom": "4px",
                                "border_bottom": f"1px solid {PALETTE['edge']}",
                            },
                        ),
                        rx.cond(
                            row["row_type"] == "item",
                            rx.link(
                                row["label"], " ↗",
                                href=row["url"], is_external=True,
                                style={"color": PALETTE["accent"], "font_size": "11px"},
                            ),
                            rx.text(
                                row["label"],
                                style={"color": PALETTE["muted"], "font_size": "11px"},
                            ),
                        ),
                    ),
                ),
                spacing="1", width="100%", align="start",
            ),
            rx.text("Run the proof demo to populate the Etherscan story.", style={"color": PALETTE["muted"]}),
        ),
        subtitle="Presentation-friendly grouped Etherscan links.",
    )

    return rx.cond(
        AppState.devtools_enabled,
        rx.vstack(intro, mode_panel, env_panel, funding_panel, buttons, roster, steps, story, width="100%", spacing="0"),
        _panel(
            "Sepolia proof demo (disabled)",
            rx.text(
                "Set AEQUITAS_DEVTOOLS=1 in your .env to enable the Sepolia "
                "proof demo. Digital Twin members are simulated at scale; "
                "Sandbox members are a small deterministic Sepolia demo set "
                "with real testnet addresses for Etherscan inspection of "
                "PIUs minted, fairness proposal flows, and investment votes.",
                style={"color": PALETTE["muted"], "font_size": "12px"},
            ),
        ),
    )


def sandbox_page() -> rx.Component:
    return shell(
        "Sandbox",
        "A small deterministic protocol lab for explainability, before/after inspection, and on-chain verification on Sepolia.",
        wallet_event_bridge(),
        protocol_status_banner(),
        _sandbox_intro(),
        rx.hstack(
            _sandbox_controls(),
            rx.box(
                rx.tabs.root(
                    rx.tabs.list(
                        rx.tabs.trigger("Scheme", value="scheme"),
                        rx.tabs.trigger("Members", value="members"),
                        rx.tabs.trigger("Fairness", value="fairness"),
                        rx.tabs.trigger("On-chain proof", value="proof"),
                        rx.tabs.trigger("Sepolia proof demo", value="sepolia_proof"),
                    ),
                    rx.tabs.content(_scheme_tab(), value="scheme", style={"padding_top": "12px"}),
                    rx.tabs.content(_members_tab(), value="members", style={"padding_top": "12px"}),
                    rx.tabs.content(_fairness_tab(), value="fairness", style={"padding_top": "12px"}),
                    rx.tabs.content(_proof_tab(), value="proof", style={"padding_top": "12px"}),
                    rx.tabs.content(_sepolia_proof_tab(), value="sepolia_proof", style={"padding_top": "12px"}),
                    default_value="scheme",
                    width="100%",
                ),
                confirm_drawer(),
                width="100%",
            ),
            spacing="4",
            align="start",
            width="100%",
        ),
        show_demo_disclaimer=False,
        show_deployment_ribbon=False,
        show_kpis=False,
    )
