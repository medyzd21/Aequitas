"""Digital Twin V2 page — interactive pension society simulator."""
from __future__ import annotations

import reflex as rx

from ..components import pill, shell, simple_table
from ..state import AppState
from ..theme import CARD_STYLE, PALETTE, SERIES


def _panel(title: str, *children, subtitle: str = "") -> rx.Component:
    return rx.box(
        rx.text(
            title,
            style={
                "color": PALETTE["text"],
                "font_weight": "600",
                "font_size": "15px",
                "margin_bottom": "4px",
            },
        ),
        rx.cond(
            subtitle != "",
            rx.text(
                subtitle,
                style={"color": PALETTE["muted"], "font_size": "11px", "margin_bottom": "10px"},
            ),
            rx.fragment(),
        ),
        *children,
        style={**CARD_STYLE, "margin_bottom": "12px"},
    )


def _kpi(label: str, value, sub: rx.Component | None = None) -> rx.Component:
    return rx.box(
        rx.text(
            label,
            style={
                "color": PALETTE["muted"],
                "font_size": "10px",
                "letter_spacing": "0.08em",
                "text_transform": "uppercase",
                "margin_bottom": "4px",
            },
        ),
        rx.text(
            value,
            style={"color": PALETTE["text"], "font_size": "20px", "font_weight": "600", "line_height": "1.2"},
        ),
        sub if sub is not None else rx.fragment(),
        style={**CARD_STYLE, "flex": "1 1 180px", "min_width": "180px"},
    )


def _story_stat(label: str, value, note) -> rx.Component:
    return rx.box(
        rx.text(label, style={"color": PALETTE["muted"], "font_size": "10px", "text_transform": "uppercase", "letter_spacing": "0.08em"}),
        rx.text(value, style={"color": PALETTE["text"], "font_size": "15px", "font_weight": "700", "margin_top": "4px"}),
        rx.text(note, style={"color": PALETTE["muted"], "font_size": "10px", "margin_top": "4px", "line_height": "1.5"}),
        style={
            "padding": "10px 12px",
            "border": f"1px solid {PALETTE['edge']}",
            "border_radius": "10px",
            "background": "rgba(15, 23, 42, 0.42)",
            "flex": "1 1 150px",
            "min_width": "150px",
        },
    )


def _toggle_row(label: str, checked, handler, help_text: str) -> rx.Component:
    return rx.hstack(
        rx.vstack(
            rx.text(label, style={"color": PALETTE["text"], "font_size": "12px", "font_weight": "500"}),
            rx.text(help_text, style={"color": PALETTE["muted"], "font_size": "10px"}),
            spacing="1",
            align="start",
        ),
        rx.spacer(),
        rx.switch(checked=checked, on_change=handler),
        align="center",
        width="100%",
    )


def _control_panel() -> rx.Component:
    return rx.box(
        rx.heading("Simulation controls", size="4", style={"color": PALETTE["text"]}),
        rx.text(
            "Set up a pension society, press run, and read the outcome like a guided simulation rather than a technical report.",
            style={"color": PALETTE["muted"], "font_size": "11px", "margin_top": "6px", "margin_bottom": "12px"},
        ),
        rx.accordion.root(
            rx.accordion.item(
                header=rx.text("Basic setup", style={"color": PALETTE["text"], "font_weight": "600", "font_size": "12px"}),
                content=rx.vstack(
                    rx.text("Baseline preset", style={"color": PALETTE["muted"], "font_size": "11px"}),
                    rx.select(
                        ["balanced", "growth", "mature", "fragile"],
                        value=AppState.twin_v2_baseline_key,
                        on_change=AppState.change_twin_v2_baseline,
                        size="2",
                        width="100%",
                    ),
                    rx.text(
                        AppState.twin_v2_baseline_description,
                        style={"color": PALETTE["muted"], "font_size": "11px", "font_style": "italic"},
                    ),
                    rx.text("Population size", style={"color": PALETTE["muted"], "font_size": "11px"}),
                    rx.input(
                        value=AppState.twin_v2_population_size.to_string(),
                        on_change=AppState.change_twin_v2_population_size,
                        type="number",
                        size="1",
                    ),
                    rx.text("From 1,000 to 100,000 people. Larger runs stay readable because the UI shows aggregates, not every person.", style={"color": PALETTE["muted"], "font_size": "10px"}),
                    rx.text("Horizon (years)", style={"color": PALETTE["muted"], "font_size": "11px"}),
                    rx.input(
                        value=AppState.twin_v2_horizon_years.to_string(),
                        on_change=AppState.change_twin_v2_horizon_years,
                        type="number",
                        size="1",
                    ),
                    rx.text("Use short horizons for fast demos and long horizons to see structural change emerge.", style={"color": PALETTE["muted"], "font_size": "10px"}),
                    spacing="2",
                    align="stretch",
                ),
                value="basic",
            ),
            rx.accordion.item(
                header=rx.text("Shock switches", style={"color": PALETTE["text"], "font_weight": "600", "font_size": "12px"}),
                content=rx.vstack(
                    _toggle_row(
                        "Random shock engine",
                        AppState.twin_v2_random_events_enabled,
                        AppState.change_twin_v2_random_events_enabled,
                        "Turn stochastic shocks on or off. When off, the society still ages structurally.",
                    ),
                    _toggle_row("Market crash", AppState.twin_v2_market_crash, AppState.change_twin_v2_market_crash, "Rare market slump that hits asset values hard."),
                    _toggle_row("Inflation shock", AppState.twin_v2_inflation_shock, AppState.change_twin_v2_inflation_shock, "Higher inflation that lingers for several years."),
                    _toggle_row("Aging society", AppState.twin_v2_aging_society, AppState.change_twin_v2_aging_society, "The membership gradually becomes older."),
                    _toggle_row("Unfair reform", AppState.twin_v2_unfair_reform, AppState.change_twin_v2_unfair_reform, "Governance proposals appear when pressure becomes uncomfortable."),
                    _toggle_row("Young stress", AppState.twin_v2_young_stress, AppState.change_twin_v2_young_stress, "Younger cohorts take more pain than older ones."),
                    spacing="3",
                    align="stretch",
                ),
                value="shocks",
            ),
            rx.accordion.item(
                header=rx.text("Advanced controls", style={"color": PALETTE["text"], "font_weight": "600", "font_size": "12px"}),
                content=rx.vstack(
                    rx.text("Random seed", style={"color": PALETTE["muted"], "font_size": "11px"}),
                    rx.input(
                        value=AppState.twin_v2_seed.to_string(),
                        on_change=AppState.change_twin_v2_seed,
                        type="number",
                        size="1",
                    ),
                    rx.text("Reuse a seed when you want the same run again.", style={"color": PALETTE["muted"], "font_size": "10px"}),
                    rx.text("Event frequency", style={"color": PALETTE["muted"], "font_size": "11px"}),
                    rx.input(
                        value=AppState.twin_v2_event_frequency.to_string(),
                        on_change=AppState.change_twin_v2_event_frequency,
                        type="number",
                        step="0.1",
                        size="1",
                    ),
                    rx.text("Higher values make shocks and pressure-driven proposals appear more often.", style={"color": PALETTE["muted"], "font_size": "10px"}),
                    rx.text("Event intensity", style={"color": PALETTE["muted"], "font_size": "11px"}),
                    rx.input(
                        value=AppState.twin_v2_event_intensity.to_string(),
                        on_change=AppState.change_twin_v2_event_intensity,
                        type="number",
                        step="0.1",
                        size="1",
                    ),
                    rx.text("Higher values make shocks bite harder when they arrive.", style={"color": PALETTE["muted"], "font_size": "10px"}),
                    spacing="2",
                    align="stretch",
                ),
                value="advanced",
            ),
            type="multiple",
            default_value=["basic", "shocks"],
            collapsible=True,
            width="100%",
        ),
        rx.button(
            "Run Digital Twin V2",
            on_click=AppState.run_twin_v2_simulation,
            color_scheme="cyan",
            size="3",
            width="100%",
            margin_top="14px",
        ),
        rx.text(
            "Built for 1k to 100k members. Most juries can stay in Basic setup and Shock switches; Advanced controls are there when you want to shape the run more precisely.",
            style={"color": PALETTE["muted"], "font_size": "10px", "margin_top": "10px"},
        ),
        style={
            **CARD_STYLE,
            "width": "310px",
            "flex_shrink": "0",
            "position": "sticky",
            "top": "92px",
            "align_self": "start",
        },
    )


def _summary_strip() -> rx.Component:
    return rx.hstack(
        _kpi(
            "Ending society",
            AppState.twin_v2_population_fmt,
            rx.text(AppState.twin_v2_active_mix_fmt, style={"color": PALETTE["muted"], "font_size": "10px"}),
        ),
        _kpi(
            "Fund assets",
            AppState.twin_v2_nav_fmt,
            rx.text(AppState.twin_v2_reserve_fmt, " reserve", style={"color": PALETTE["muted"], "font_size": "10px"}),
        ),
        _kpi(
            "Funding health",
            AppState.twin_v2_funded_ratio_fmt,
            rx.match(
                AppState.twin_v2_funded_pill,
                ("good", pill("Healthy", "good")),
                ("warn", pill("Watch", "warn")),
                ("bad", pill("Stress", "bad")),
                pill("No run", "muted"),
            ),
        ),
        _kpi(
            "Fairness",
            AppState.twin_v2_average_gini_fmt,
            rx.hstack(
                rx.match(
                    AppState.twin_v2_fairness_pill,
                    ("good", pill("Balanced", "good")),
                    ("warn", pill("Monitor", "warn")),
                    ("bad", pill("Uneven", "bad")),
                    pill("No run", "muted"),
                ),
                rx.text(AppState.twin_v2_average_stress_fmt, " stress pass", style={"color": PALETTE["muted"], "font_size": "10px"}),
                spacing="2",
                align="center",
            ),
        ),
        _kpi("Average member age", AppState.twin_v2_average_age_fmt, rx.text(AppState.twin_v2_average_salary_fmt, " active pay", style={"color": PALETTE["muted"], "font_size": "10px"})),
        _kpi(
            "PIU price",
            AppState.twin_v2_piu_price_fmt,
            rx.text("CPI ", AppState.twin_v2_cpi_fmt, style={"color": PALETTE["muted"], "font_size": "10px"}),
        ),
        _kpi("Simulation events", AppState.twin_v2_event_count_fmt, rx.text(AppState.twin_v2_proposal_count_fmt, " governance proposals", style={"color": PALETTE["muted"], "font_size": "10px"})),
        width="100%",
        wrap="wrap",
        spacing="3",
        align="stretch",
    )


def _run_summary_panel() -> rx.Component:
    return _panel(
        "What happened in this run?",
        rx.cond(
            AppState.twin_v2_ran,
            rx.vstack(
                rx.text(
                    AppState.twin_v2_run_summary,
                    style={"color": PALETTE["text"], "font_size": "13px", "line_height": "1.7"},
                ),
                rx.hstack(
                    rx.foreach(
                        AppState.twin_v2_run_highlights,
                        lambda row: rx.box(
                            rx.text(row["label"], style={"color": PALETTE["muted"], "font_size": "10px", "text_transform": "uppercase", "letter_spacing": "0.08em"}),
                            rx.text(row["value"], style={"color": PALETTE["text"], "font_size": "13px", "font_weight": "600"}),
                            style={
                                "padding": "10px 12px",
                                "border_radius": "10px",
                                "border": f"1px solid {PALETTE['edge']}",
                                "background": "rgba(15, 23, 42, 0.55)",
                                "min_width": "120px",
                            },
                        ),
                    ),
                    wrap="wrap",
                    spacing="3",
                    width="100%",
                ),
                spacing="3",
                align="start",
                width="100%",
            ),
            _empty("Run the simulator to get a plain-English summary of what happened."),
        ),
        subtitle="This is the short, jury-friendly narrative of the whole run: setup, shocks, governance, fairness, and reserve use.",
    )


def _empty(message: str) -> rx.Component:
    return rx.text(message, style={"color": PALETTE["muted"], "font_size": "12px"})


def _population_primary_chart() -> rx.Component:
    return rx.match(
        AppState.twin_v2_population_mode,
        (
            "share",
            rx.recharts.area_chart(
                rx.recharts.area(data_key="active_share_pct", name="Active share (%)", stack_id="mix", fill=SERIES[0], stroke=SERIES[0]),
                rx.recharts.area(data_key="retired_share_pct", name="Retired share (%)", stack_id="mix", fill=SERIES[2], stroke=SERIES[2]),
                rx.recharts.area(data_key="deceased_share_pct", name="Deceased share (%)", stack_id="mix", fill=SERIES[3], stroke=SERIES[3]),
                rx.recharts.x_axis(data_key="year", stroke=PALETTE["muted"]),
                rx.recharts.y_axis(stroke=PALETTE["muted"]),
                rx.recharts.cartesian_grid(stroke=PALETTE["edge"]),
                rx.recharts.legend(),
                rx.recharts.graphing_tooltip(),
                data=AppState.twin_v2_annual_rows,
                width="100%",
                height=280,
            ),
        ),
        rx.recharts.area_chart(
            rx.recharts.area(data_key="active_count", name="Active members", stack_id="mix", fill=SERIES[0], stroke=SERIES[0]),
            rx.recharts.area(data_key="retired_count", name="Retired members", stack_id="mix", fill=SERIES[2], stroke=SERIES[2]),
            rx.recharts.area(data_key="deceased_count", name="Deceased members", stack_id="mix", fill=SERIES[3], stroke=SERIES[3]),
            rx.recharts.x_axis(data_key="year", stroke=PALETTE["muted"]),
            rx.recharts.y_axis(stroke=PALETTE["muted"]),
            rx.recharts.cartesian_grid(stroke=PALETTE["edge"]),
            rx.recharts.legend(),
            rx.recharts.graphing_tooltip(),
            data=AppState.twin_v2_annual_rows,
            width="100%",
            height=280,
        ),
    )


def _fund_chart() -> rx.Component:
    return rx.match(
        AppState.twin_v2_fund_view,
        (
            "flows",
            rx.recharts.line_chart(
                rx.recharts.line(data_key="contributions_m", name="Contributions (£m)", stroke=PALETTE["good"], stroke_width=2, dot=False),
                rx.recharts.line(data_key="benefits_m", name="Benefits paid (£m)", stroke=PALETTE["warn"], stroke_width=2, dot=False),
                rx.recharts.x_axis(data_key="year", stroke=PALETTE["muted"]),
                rx.recharts.y_axis(stroke=PALETTE["muted"]),
                rx.recharts.cartesian_grid(stroke=PALETTE["edge"]),
                rx.recharts.legend(),
                rx.recharts.graphing_tooltip(),
                data=AppState.twin_v2_annual_rows,
                width="100%",
                height=280,
            ),
        ),
        (
            "per_member",
            rx.recharts.line_chart(
                rx.recharts.line(data_key="nav_per_member", name="Assets per member (£)", stroke=PALETTE["accent"], stroke_width=2, dot=False),
                rx.recharts.line(data_key="reserve_per_member", name="Reserve per member (£)", stroke=SERIES[1], stroke_width=2, dot=False),
                rx.recharts.line(data_key="benefits_per_member", name="Benefits per member (£)", stroke=PALETTE["warn"], stroke_width=2, dot=False),
                rx.recharts.x_axis(data_key="year", stroke=PALETTE["muted"]),
                rx.recharts.y_axis(stroke=PALETTE["muted"]),
                rx.recharts.cartesian_grid(stroke=PALETTE["edge"]),
                rx.recharts.legend(),
                rx.recharts.graphing_tooltip(),
                data=AppState.twin_v2_annual_rows,
                width="100%",
                height=280,
            ),
        ),
        (
            "indexed",
            rx.recharts.line_chart(
                rx.recharts.line(data_key="fund_nav_index", name="Assets (index)", stroke=PALETTE["accent"], stroke_width=2, dot=False),
                rx.recharts.line(data_key="reserve_index", name="Reserve (index)", stroke=SERIES[1], stroke_width=2, dot=False),
                rx.recharts.line(data_key="benefits_index", name="Benefits (index)", stroke=PALETTE["warn"], stroke_width=2, dot=False),
                rx.recharts.x_axis(data_key="year", stroke=PALETTE["muted"]),
                rx.recharts.y_axis(stroke=PALETTE["muted"]),
                rx.recharts.reference_line(y=1, stroke=PALETTE["muted"], stroke_dasharray="4 4"),
                rx.recharts.cartesian_grid(stroke=PALETTE["edge"]),
                rx.recharts.legend(),
                rx.recharts.graphing_tooltip(),
                data=AppState.twin_v2_annual_rows,
                width="100%",
                height=280,
            ),
        ),
        rx.recharts.line_chart(
            rx.recharts.line(data_key="fund_nav_m", name="Fund assets (£m)", stroke=PALETTE["accent"], stroke_width=2, dot=False),
            rx.recharts.line(data_key="reserve_m", name="Reserve (£m)", stroke=SERIES[1], stroke_width=2, dot=False, stroke_dasharray="5 4"),
            rx.recharts.x_axis(data_key="year", stroke=PALETTE["muted"]),
            rx.recharts.y_axis(stroke=PALETTE["muted"]),
            rx.recharts.cartesian_grid(stroke=PALETTE["edge"]),
            rx.recharts.legend(),
            rx.recharts.graphing_tooltip(),
            data=AppState.twin_v2_annual_rows,
            width="100%",
            height=280,
        ),
    )


def _fairness_chart() -> rx.Component:
    return rx.match(
        AppState.twin_v2_fairness_view,
        (
            "stress",
            rx.recharts.line_chart(
                rx.recharts.line(data_key="stress_pass_pct", name="Stress pass (%)", stroke=PALETTE["good"], stroke_width=2, dot=False),
                rx.recharts.line(data_key="stress_p95_gini_pct", name="P95 fairness gap (%)", stroke=PALETTE["warn"], stroke_width=2, dot=False),
                rx.recharts.line(data_key="youngest_poor_pct", name="Youngest cohort below floor (%)", stroke=PALETTE["bad"], stroke_width=2, dot=False),
                rx.recharts.x_axis(data_key="year", stroke=PALETTE["muted"]),
                rx.recharts.y_axis(stroke=PALETTE["muted"]),
                rx.recharts.cartesian_grid(stroke=PALETTE["edge"]),
                rx.recharts.legend(),
                rx.recharts.graphing_tooltip(),
                data=AppState.twin_v2_annual_rows,
                width="100%",
                height=280,
            ),
        ),
        rx.recharts.line_chart(
            rx.recharts.line(data_key="gini_pct", name="Fairness gap (%)", stroke=PALETTE["bad"], stroke_width=2, dot=False),
            rx.recharts.line(data_key="intergen_pct", name="Intergenerational balance (%)", stroke=PALETTE["good"], stroke_width=2, dot=False),
            rx.recharts.line(data_key="stress_pass_pct", name="Stress pass (%)", stroke=PALETTE["accent"], stroke_width=2, dot=False),
            rx.recharts.x_axis(data_key="year", stroke=PALETTE["muted"]),
            rx.recharts.y_axis(stroke=PALETTE["muted"]),
            rx.recharts.cartesian_grid(stroke=PALETTE["edge"]),
            rx.recharts.legend(),
            rx.recharts.graphing_tooltip(),
            data=AppState.twin_v2_annual_rows,
            width="100%",
            height=280,
        ),
    )


def _selected_story_chart() -> rx.Component:
    return rx.recharts.line_chart(
        rx.recharts.line(data_key="nominal_piu_value_k", name="Indexed pension value (£k)", stroke=PALETTE["accent"], stroke_width=2, dot=False),
        rx.recharts.line(data_key="salary_k", name="Salary (£k)", stroke=PALETTE["good"], stroke_width=2, dot=False),
        rx.recharts.line(data_key="annual_benefit_k", name="Annual pension (£k)", stroke=PALETTE["warn"], stroke_width=2, dot=False),
        rx.recharts.x_axis(data_key="year", stroke=PALETTE["muted"]),
        rx.recharts.y_axis(stroke=PALETTE["muted"]),
        rx.recharts.cartesian_grid(stroke=PALETTE["edge"]),
        rx.recharts.legend(),
        rx.recharts.graphing_tooltip(),
        data=AppState.twin_v2_selected_story_rows,
        width="100%",
        height=280,
    )


def _selected_story_units_chart() -> rx.Component:
    return rx.recharts.line_chart(
        rx.recharts.line(data_key="piu_balance_k", name="PIU balance (k units)", stroke=SERIES[1], stroke_width=2, dot=False),
        rx.recharts.line(data_key="benefit_piu_k", name="Pension units (k)", stroke=PALETTE["warn"], stroke_width=2, dot=False),
        rx.recharts.x_axis(data_key="year", stroke=PALETTE["muted"]),
        rx.recharts.y_axis(stroke=PALETTE["muted"]),
        rx.recharts.cartesian_grid(stroke=PALETTE["edge"]),
        rx.recharts.legend(),
        rx.recharts.graphing_tooltip(),
        data=AppState.twin_v2_selected_story_rows,
        width="100%",
        height=220,
    )


def _status_badge(status) -> rx.Component:
    return rx.match(
        status,
        ("Active", pill("Active", "good")),
        ("Retired", pill("Retired", "warn")),
        ("Deceased", pill("Deceased", "muted")),
        pill("Profile", "muted"),
    )


def _story_card(row) -> rx.Component:
    selected = AppState.twin_v2_story_key == row["key"]
    return rx.box(
        rx.hstack(
            rx.vstack(
                rx.hstack(
                    rx.text(row["label"], style={"color": PALETTE["text"], "font_weight": "700", "font_size": "13px"}),
                    _status_badge(row["status"]),
                    spacing="2",
                    align="center",
                ),
                rx.text(row["description"], style={"color": PALETTE["muted"], "font_size": "10px"}),
                rx.text(row["narrative"], style={"color": PALETTE["muted"], "font_size": "10px"}),
                rx.text(row["turning_point"], style={"color": PALETTE["text"], "font_size": "10px"}),
                spacing="1",
                align="start",
            ),
            rx.spacer(),
            rx.vstack(
                rx.text(row["piu_value"], style={"color": PALETTE["text"], "font_size": "11px", "font_weight": "600"}),
                rx.text("PIU value at end", style={"color": PALETTE["muted"], "font_size": "10px"}),
                rx.text(row["annual_benefit"], style={"color": PALETTE["muted"], "font_size": "11px"}),
                rx.text("Annual pension at end", style={"color": PALETTE["muted"], "font_size": "10px"}),
                spacing="1",
                align="end",
            ),
            align="center",
            width="100%",
        ),
        rx.hstack(
            rx.text(
                rx.cond(selected, "Selected story", "Open story"),
                style={
                    "color": rx.cond(selected, PALETTE["accent"], PALETTE["muted"]),
                    "font_size": "11px",
                    "font_weight": "600",
                },
            ),
            rx.spacer(),
            rx.text(
                "Tap to focus the chart and lifecycle summary",
                style={"color": PALETTE["muted"], "font_size": "10px"},
            ),
            width="100%",
            margin_top="8px",
            align="center",
        ),
        on_click=AppState.change_twin_v2_story_key(row["key"]),
        style={
            "padding": "12px 14px",
            "border": rx.cond(
                selected,
                f"1px solid {PALETTE['accent']}",
                f"1px solid {PALETTE['edge']}",
            ),
            "box_shadow": rx.cond(
                selected,
                "0 0 0 1px rgba(56, 189, 248, 0.25)",
                "none",
            ),
            "border_radius": "12px",
            "background": rx.cond(
                selected,
                "rgba(8, 47, 73, 0.42)",
                "rgba(15, 23, 42, 0.45)",
            ),
            "cursor": "pointer",
            "_hover": {"border_color": PALETTE["accent"]},
        },
    )


def _population_tab() -> rx.Component:
    return rx.vstack(
        _panel(
            "Population through time",
            rx.hstack(
                rx.text("View", style={"color": PALETTE["muted"], "font_size": "11px"}),
                rx.select(
                    ["absolute", "share"],
                    value=AppState.twin_v2_population_mode,
                    on_change=AppState.change_twin_v2_population_mode,
                    size="1",
                    width="140px",
                ),
                rx.spacer(),
                align="center",
                width="100%",
                margin_bottom="10px",
            ),
            rx.cond(
                AppState.twin_v2_annual_rows.length() > 0,
                _population_primary_chart(),
                _empty("Run the simulation to see how the society evolves."),
            ),
            subtitle="Switch between headcount and composition share to avoid hiding the member mix.",
        ),
        rx.hstack(
            _panel(
                "Entry, retirement, and mortality flow",
                rx.cond(
                    AppState.twin_v2_annual_rows.length() > 0,
                    rx.recharts.line_chart(
                        rx.recharts.line(data_key="entrant_count", stroke=PALETTE["good"], stroke_width=2, dot=False),
                        rx.recharts.line(data_key="retirement_count", stroke=PALETTE["warn"], stroke_width=2, dot=False),
                        rx.recharts.line(data_key="death_count", stroke=PALETTE["bad"], stroke_width=2, dot=False),
                        rx.recharts.x_axis(data_key="year", stroke=PALETTE["muted"]),
                        rx.recharts.y_axis(stroke=PALETTE["muted"]),
                        rx.recharts.cartesian_grid(stroke=PALETTE["edge"]),
                        rx.recharts.legend(),
                        rx.recharts.graphing_tooltip(),
                        data=AppState.twin_v2_annual_rows,
                        width="100%",
                        height=250,
                    ),
                    _empty("No flow history yet."),
                ),
                subtitle="This separates turnover from the stock chart so member churn stays interpretable.",
            ),
            _panel(
                "Cohort fairness snapshot",
                rx.cond(
                    AppState.twin_v2_focus_cohort_rows.length() > 0,
                    rx.vstack(
                        rx.recharts.bar_chart(
                            rx.recharts.bar(data_key="money_worth_ratio", fill=PALETTE["accent"]),
                            rx.recharts.x_axis(data_key="cohort", stroke=PALETTE["muted"]),
                            rx.recharts.y_axis(stroke=PALETTE["muted"]),
                            rx.recharts.reference_line(y=1, stroke=PALETTE["muted"], stroke_dasharray="4 4"),
                            rx.recharts.cartesian_grid(stroke=PALETTE["edge"]),
                            rx.recharts.graphing_tooltip(),
                            data=AppState.twin_v2_focus_cohort_rows,
                            width="100%",
                            height=250,
                        ),
                        rx.text(AppState.twin_v2_cohort_focus_note, style={"color": PALETTE["muted"], "font_size": "10px"}),
                        spacing="2",
                        width="100%",
                    ),
                    _empty("No cohort snapshot yet."),
                ),
                subtitle="Latest-year cohort MWR, with a readable subset when the society spans many cohorts.",
            ),
            spacing="3",
            width="100%",
            align="stretch",
        ),
        width="100%",
        spacing="0",
    )


def _fund_tab() -> rx.Component:
    return rx.vstack(
        _panel(
            "Fund dynamics",
            rx.hstack(
                rx.text("Metric set", style={"color": PALETTE["muted"], "font_size": "11px"}),
                rx.select(
                    ["assets", "flows", "per_member", "indexed"],
                    value=AppState.twin_v2_fund_view,
                    on_change=AppState.change_twin_v2_fund_view,
                    size="1",
                    width="160px",
                ),
                rx.spacer(),
                align="center",
                width="100%",
                margin_bottom="10px",
            ),
            rx.cond(
                AppState.twin_v2_annual_rows.length() > 0,
                _fund_chart(),
                _empty("Run the simulation to inspect fund paths."),
            ),
            subtitle="NAV, reserve, flows, and per-member views are separated so unlike-scaled series do not flatten each other.",
        ),
        rx.hstack(
            _panel(
                "CPI and PIU price path",
                rx.cond(
                    AppState.twin_v2_annual_rows.length() > 0,
                    rx.recharts.line_chart(
                        rx.recharts.line(data_key="cpi_rebased", name="CPI (base=100)", stroke=PALETTE["accent"], stroke_width=2, dot=False),
                        rx.recharts.line(data_key="piu_price_index", name="PIU price (base=100)", stroke=SERIES[1], stroke_width=2, dot=False),
                        rx.recharts.x_axis(data_key="year", stroke=PALETTE["muted"]),
                        rx.recharts.y_axis(stroke=PALETTE["muted"]),
                        rx.recharts.reference_line(y=100, stroke=PALETTE["muted"], stroke_dasharray="4 4"),
                        rx.recharts.cartesian_grid(stroke=PALETTE["edge"]),
                        rx.recharts.legend(),
                        rx.recharts.graphing_tooltip(),
                        data=AppState.twin_v2_annual_rows,
                        width="100%",
                        height=250,
                    ),
                    _empty("Run the simulation to see CPI and PIU pricing."),
                ),
                subtitle="Both series are rebased to 100 in the first year, so the explicit index rule is easy to read.",
            ),
            _panel(
                "Contribution purchasing power",
                rx.cond(
                    AppState.twin_v2_annual_rows.length() > 0,
                    rx.recharts.line_chart(
                        rx.recharts.line(data_key="pius_per_1000", name="PIUs bought per £1,000", stroke=PALETTE["good"], stroke_width=2, dot=False),
                        rx.recharts.x_axis(data_key="year", stroke=PALETTE["muted"]),
                        rx.recharts.y_axis(stroke=PALETTE["muted"]),
                        rx.recharts.cartesian_grid(stroke=PALETTE["edge"]),
                        rx.recharts.graphing_tooltip(),
                        data=AppState.twin_v2_annual_rows,
                        width="100%",
                        height=250,
                    ),
                    _empty("Run the simulation to see how much pension purchasing power each contribution buys."),
                ),
                subtitle="When inflation pushes the PIU price up, the same nominal contribution buys fewer pension units.",
            ),
            spacing="3",
            width="100%",
            align="stretch",
        ),
        rx.hstack(
            _panel(
                "Funding and pressure",
                rx.cond(
                    AppState.twin_v2_annual_rows.length() > 0,
                    rx.recharts.line_chart(
                        rx.recharts.line(data_key="funded_ratio_pct", name="Funded ratio (%)", stroke=PALETTE["good"], stroke_width=2, dot=False),
                        rx.recharts.line(data_key="reserve_ratio_pct", name="Reserve share (%)", stroke=SERIES[1], stroke_width=2, dot=False),
                        rx.recharts.line(data_key="event_pressure_pct", name="Pressure score (%)", stroke=PALETTE["bad"], stroke_width=2, dot=False),
                        rx.recharts.x_axis(data_key="year", stroke=PALETTE["muted"]),
                        rx.recharts.y_axis(stroke=PALETTE["muted"]),
                        rx.recharts.reference_line(y=100, stroke=PALETTE["muted"], stroke_dasharray="4 4"),
                        rx.recharts.cartesian_grid(stroke=PALETTE["edge"]),
                        rx.recharts.legend(),
                        rx.recharts.graphing_tooltip(),
                        data=AppState.twin_v2_annual_rows,
                        width="100%",
                        height=260,
                    ),
                    _empty("Funding pressure appears once the simulation runs."),
                ),
                subtitle="Reserve pressure is tracked separately from assets so backstop dependence is visible early.",
            ),
            _panel(
                "Indexed liabilities versus assets",
                rx.cond(
                    AppState.twin_v2_annual_rows.length() > 0,
                    rx.recharts.line_chart(
                        rx.recharts.line(data_key="indexed_liability_m", name="Indexed liability (£m)", stroke=PALETTE["warn"], stroke_width=2, dot=False),
                        rx.recharts.line(data_key="fund_nav_m", name="Fund assets (£m)", stroke=PALETTE["accent"], stroke_width=2, dot=False),
                        rx.recharts.line(data_key="reserve_m", name="Reserve (£m)", stroke=SERIES[1], stroke_width=2, dot=False, stroke_dasharray="5 4"),
                        rx.recharts.x_axis(data_key="year", stroke=PALETTE["muted"]),
                        rx.recharts.y_axis(stroke=PALETTE["muted"]),
                        rx.recharts.cartesian_grid(stroke=PALETTE["edge"]),
                        rx.recharts.legend(),
                        rx.recharts.graphing_tooltip(),
                        data=AppState.twin_v2_annual_rows,
                        width="100%",
                        height=260,
                    ),
                    _empty("Indexed liabilities appear once the simulation runs."),
                ),
                subtitle="This is where inflation pressure becomes visible: the liability side can climb faster than the asset side.",
            ),
            spacing="3",
            width="100%",
            align="stretch",
        ),
        _panel(
            "Mortality learning",
            rx.cond(
                AppState.twin_v2_mortality_rows.length() > 0,
                rx.vstack(
                    rx.text(
                        "Mortality does not stay frozen forever. The Twin starts from a Gompertz-Makeham prior, compares that prior with observed fund deaths and exposure, then blends toward fund-specific experience only as credibility builds.",
                        style={"color": PALETTE["text"], "font_size": "12px", "line_height": "1.7"},
                    ),
                    rx.hstack(
                        rx.foreach(
                            AppState.twin_v2_mortality_summary_rows,
                            lambda row: rx.box(
                                rx.text(row["label"], style={"color": PALETTE["muted"], "font_size": "10px", "text_transform": "uppercase", "letter_spacing": "0.08em"}),
                                rx.text(row["value"], style={"color": PALETTE["text"], "font_size": "13px", "font_weight": "600"}),
                                style={
                                    "padding": "10px 12px",
                                    "border_radius": "10px",
                                    "border": f"1px solid {PALETTE['edge']}",
                                    "background": "rgba(15, 23, 42, 0.55)",
                                    "min_width": "150px",
                                },
                            ),
                        ),
                        wrap="wrap",
                        spacing="3",
                        width="100%",
                    ),
                    rx.hstack(
                        _panel(
                            "Credibility and experience",
                            rx.recharts.line_chart(
                                rx.recharts.line(data_key="credibility_pct", name="Credibility (%)", stroke=PALETTE["good"], stroke_width=2, dot=False),
                                rx.recharts.line(data_key="observed_expected", name="Observed / expected deaths", stroke=PALETTE["warn"], stroke_width=2, dot=False),
                                rx.recharts.x_axis(data_key="year", stroke=PALETTE["muted"]),
                                rx.recharts.y_axis(stroke=PALETTE["muted"]),
                                rx.recharts.cartesian_grid(stroke=PALETTE["edge"]),
                                rx.recharts.legend(),
                                rx.recharts.graphing_tooltip(),
                                data=AppState.twin_v2_mortality_rows,
                                width="100%",
                                height=240,
                            ),
                            subtitle="Credibility stays low when the study is thin, then rises only when enough exposure and deaths accumulate.",
                        ),
                        _panel(
                            "Liability impact of the active basis",
                            rx.recharts.line_chart(
                                rx.recharts.line(data_key="indexed_liability_m", name="Indexed liability (£m)", stroke=PALETTE["warn"], stroke_width=2, dot=False),
                                rx.recharts.line(data_key="funded_ratio_pct", name="Funded ratio (%)", stroke=PALETTE["accent"], stroke_width=2, dot=False),
                                rx.recharts.line(data_key="mortality_multiplier_pct", name="Mortality adjustment vs prior (%)", stroke=SERIES[1], stroke_width=2, dot=False),
                                rx.recharts.x_axis(data_key="year", stroke=PALETTE["muted"]),
                                rx.recharts.y_axis(stroke=PALETTE["muted"]),
                                rx.recharts.cartesian_grid(stroke=PALETTE["edge"]),
                                rx.recharts.legend(),
                                rx.recharts.graphing_tooltip(),
                                data=AppState.twin_v2_annual_rows,
                                width="100%",
                                height=240,
                            ),
                            subtitle="When experience says members are living longer or shorter than the prior expected, indexed liabilities and funded status move with it.",
                        ),
                        spacing="3",
                        width="100%",
                        align="stretch",
                    ),
                    rx.text(
                        AppState.twin_v2_mortality_effect_text,
                        style={"color": PALETTE["muted"], "font_size": "11px", "line_height": "1.7"},
                    ),
                    spacing="3",
                    width="100%",
                    align="start",
                ),
                _empty("Run the simulation to see the baseline prior, observed experience, credibility build-up, and the active mortality basis."),
            ),
            subtitle="Blockchain is only needed to publish the active mortality basis version and its proof hash. Raw death records, exposures, and calibration stay off-chain.",
        ),
        width="100%",
        spacing="0",
    )


def _fairness_tab() -> rx.Component:
    return rx.vstack(
        _panel(
            "Fairness dashboard",
            rx.hstack(
                rx.text("View", style={"color": PALETTE["muted"], "font_size": "11px"}),
                rx.select(
                    ["equity", "stress"],
                    value=AppState.twin_v2_fairness_view,
                    on_change=AppState.change_twin_v2_fairness_view,
                    size="1",
                    width="140px",
                ),
                rx.spacer(),
                align="center",
                width="100%",
                margin_bottom="10px",
            ),
            rx.cond(
                AppState.twin_v2_annual_rows.length() > 0,
                _fairness_chart(),
                _empty("Run the simulation to populate fairness metrics."),
            ),
            subtitle="Equity view focuses on cohort fairness; stress view shows how often the scheme remains acceptable under stochastic pressure.",
        ),
        rx.hstack(
            _panel(
                "Scheme balance",
                rx.cond(
                    AppState.twin_v2_annual_rows.length() > 0,
                    rx.recharts.line_chart(
                        rx.recharts.line(data_key="scheme_mwr", name="Scheme MWR", stroke=PALETTE["accent"], stroke_width=2, dot=False),
                        rx.recharts.line(data_key="funded_ratio", name="Funded ratio", stroke=PALETTE["good"], stroke_width=2, dot=False),
                        rx.recharts.x_axis(data_key="year", stroke=PALETTE["muted"]),
                        rx.recharts.y_axis(stroke=PALETTE["muted"]),
                        rx.recharts.reference_line(y=1, stroke=PALETTE["muted"], stroke_dasharray="4 4"),
                        rx.recharts.cartesian_grid(stroke=PALETTE["edge"]),
                        rx.recharts.legend(),
                        rx.recharts.graphing_tooltip(),
                        data=AppState.twin_v2_annual_rows,
                        width="100%",
                        height=250,
                    ),
                    _empty("Run the simulation to see whether value and funding stay in balance."),
                ),
                subtitle="Scheme value and funding are shown separately from fairness percentages so the scales stay honest.",
            ),
            _panel(
                "Latest cohort stress",
                rx.cond(
                    AppState.twin_v2_focus_cohort_rows.length() > 0,
                    rx.recharts.bar_chart(
                        rx.recharts.bar(data_key="stress_load", name="Stress load", fill=PALETTE["warn"]),
                        rx.recharts.x_axis(data_key="cohort", stroke=PALETTE["muted"]),
                        rx.recharts.y_axis(stroke=PALETTE["muted"]),
                        rx.recharts.cartesian_grid(stroke=PALETTE["edge"]),
                        rx.recharts.graphing_tooltip(),
                        data=AppState.twin_v2_focus_cohort_rows,
                        width="100%",
                        height=250,
                    ),
                    _empty("No cohort stress snapshot yet."),
                ),
                subtitle="At a glance, this shows which cohorts are carrying the most simulated pressure in the latest year.",
            ),
            spacing="3",
            width="100%",
            align="stretch",
        ),
        _panel(
            "Governance proposals triggered by unfair reforms",
            rx.cond(
                AppState.twin_v2_proposal_rows.length() > 0,
                rx.box(
                    simple_table(
                        [
                            ("year", "Year"),
                            ("proposal", "Proposal"),
                            ("target_cohort", "Target cohort"),
                            ("before_mwr", "Before MWR"),
                            ("after_mwr", "After MWR"),
                            ("passed", "Pass / fail"),
                            ("contract_action", "On-chain mapping"),
                            ("reason", "Plain-English explanation"),
                        ],
                        AppState.twin_v2_proposal_rows,
                    ),
                    style={"overflow_x": "auto"},
                ),
                _empty("No unfair reform proposal has been triggered in this run."),
            ),
            subtitle="Each proposal shows before/after cohort MWR, corridor verdict, plain-English rationale, and the contract action it would map to.",
        ),
        width="100%",
        spacing="0",
    )


def _events_tab() -> rx.Component:
    return rx.vstack(
        rx.hstack(
            _panel(
                "Event mix",
                rx.cond(
                    AppState.twin_v2_event_mix_rows.length() > 0,
                    rx.recharts.bar_chart(
                        rx.recharts.bar(data_key="count", fill=PALETTE["accent"]),
                        rx.recharts.x_axis(data_key="label", stroke=PALETTE["muted"]),
                        rx.recharts.y_axis(stroke=PALETTE["muted"]),
                        rx.recharts.cartesian_grid(stroke=PALETTE["edge"]),
                        rx.recharts.graphing_tooltip(),
                        data=AppState.twin_v2_event_mix_rows,
                        width="100%",
                        height=260,
                    ),
                    _empty("Event counts appear after a run."),
                ),
                subtitle="Counts of the different event types that actually occurred in this simulation.",
            ),
            _panel(
                "Why events matter",
                rx.vstack(
                    rx.text(
                        "Market crashes are rare heavy-tail shocks. Inflation regimes persist across years. "
                        "Aging drift changes the society slowly. Young stress hurts younger workers more. "
                        "Unfair reform proposals only appear when pressure is high enough.",
                        style={"color": PALETTE["text"], "font_size": "12px", "line_height": "1.6"},
                    ),
                    rx.text(
                        "This keeps the twin event-driven rather than preset-driven: the same baseline can tell different stories depending on the seed and pressure path.",
                        style={"color": PALETTE["muted"], "font_size": "11px", "line_height": "1.6"},
                    ),
                    spacing="3",
                    align="start",
                ),
                subtitle="Plain-English event model for a non-technical jury.",
            ),
            spacing="3",
            width="100%",
            align="stretch",
        ),
        _panel(
            "Major moments and responses",
            rx.cond(
                AppState.twin_v2_event_story_rows.length() > 0,
                rx.vstack(
                    rx.foreach(
                        AppState.twin_v2_event_story_rows,
                        lambda row: rx.box(
                            rx.hstack(
                                rx.vstack(
                                    rx.hstack(
                                        rx.text(row["headline"], style={"color": PALETTE["text"], "font_weight": "700", "font_size": "13px"}),
                                        pill(row["classification_label"], "muted"),
                                        spacing="2",
                                        align="center",
                                    ),
                                    rx.text("Year ", row["year"].to_string(), style={"color": PALETTE["muted"], "font_size": "10px"}),
                                    rx.text(row["what_happened"], style={"color": PALETTE["text"], "font_size": "12px", "line_height": "1.6"}),
                                    rx.text("Why it matters: ", row["why_it_matters"], style={"color": PALETTE["muted"], "font_size": "11px", "line_height": "1.6"}),
                                    rx.text("Protocol response: ", row["protocol_response"], style={"color": PALETTE["muted"], "font_size": "11px", "line_height": "1.6"}),
                                    spacing="1",
                                    align="start",
                                ),
                                rx.spacer(),
                                rx.vstack(
                                    rx.text("Technical mapping", style={"color": PALETTE["muted"], "font_size": "10px", "text_transform": "uppercase", "letter_spacing": "0.08em"}),
                                    rx.code(row["contract_action"], style={"color": PALETTE["text"], "font_size": "11px"}),
                                    spacing="1",
                                    align="end",
                                ),
                                width="100%",
                                align="start",
                            ),
                            style={
                                "padding": "12px 14px",
                                "border": f"1px solid {PALETTE['edge']}",
                                "border_radius": "12px",
                                "background": "rgba(15, 23, 42, 0.45)",
                            },
                        ),
                    ),
                    spacing="3",
                    width="100%",
                ),
                _empty("No events to show yet."),
            ),
            subtitle="Each moment explains what happened, why it mattered, and what the protocol did in response.",
        ),
        width="100%",
        spacing="0",
    )


def _stories_tab() -> rx.Component:
    return rx.vstack(
        _panel(
            "Representative stories",
            rx.foreach(
                AppState.twin_v2_story_summary_rows,
                _story_card,
            ),
            subtitle="The UI stores only a small set of sampled personas so the twin stays legible even when the simulated society is very large.",
        ),
        rx.hstack(
            _panel(
                "Selected story",
                rx.cond(
                    AppState.twin_v2_selected_story_rows.length() > 0,
                    rx.vstack(
                        rx.hstack(
                            rx.vstack(
                                rx.hstack(
                                    rx.text(AppState.twin_v2_selected_story["label"], style={"color": PALETTE["text"], "font_size": "16px", "font_weight": "700"}),
                                    _status_badge(AppState.twin_v2_selected_story["status"]),
                                    spacing="2",
                                    align="center",
                                ),
                                rx.text(AppState.twin_v2_selected_story_note, style={"color": PALETTE["text"], "font_size": "12px", "line_height": "1.6"}),
                                rx.text(AppState.twin_v2_selected_story_status_note, style={"color": PALETTE["muted"], "font_size": "11px", "line_height": "1.6"}),
                                spacing="2",
                                align="start",
                            ),
                            width="100%",
                            align="start",
                        ),
                        rx.hstack(
                            _story_stat("Start age", AppState.twin_v2_selected_story["start_age"].to_string(), "Age at the beginning of the run"),
                            _story_stat("Retirement age", AppState.twin_v2_selected_story["retirement_age"].to_string(), "Target retirement trigger"),
                            _story_stat("PIU value", AppState.twin_v2_selected_story["piu_value"], "Current nominal value of accumulated PIUs"),
                            _story_stat("PIU price", AppState.twin_v2_selected_story["piu_price_display"], "Current cash price of one PIU"),
                            _story_stat("Unit position", AppState.twin_v2_selected_story["unit_position"], AppState.twin_v2_selected_story["unit_position_note"]),
                            spacing="3",
                            width="100%",
                            wrap="wrap",
                            align="stretch",
                        ),
                        _selected_story_chart(),
                        _selected_story_units_chart(),
                        spacing="3",
                        width="100%",
                        align="start",
                    ),
                    _empty("Representative stories appear after the first run."),
                ),
                subtitle="When a member retires or dies, the chart explains why the path changes instead of leaving the user guessing.",
            ),
            _panel(
                "Lifecycle checkpoints",
                rx.cond(
                    AppState.twin_v2_selected_story_rows.length() > 0,
                    rx.vstack(
                        rx.text(AppState.twin_v2_selected_story["narrative"], style={"color": PALETTE["text"], "font_size": "12px", "line_height": "1.6"}),
                        rx.text(AppState.twin_v2_selected_story["turning_point"], style={"color": PALETTE["text"], "font_size": "12px", "line_height": "1.6"}),
                        rx.text(
                            "If the person is retired, accumulated PIUs have already been converted into pension units. If the person is deceased, flat or near-zero values after death are expected and reflect the simulation rules rather than a broken chart.",
                            style={"color": PALETTE["muted"], "font_size": "11px", "line_height": "1.6"},
                        ),
                        spacing="3",
                        align="start",
                    ),
                    _empty("Select a story to see its lifecycle checkpoints."),
                ),
            ),
            spacing="3",
            width="100%",
            align="stretch",
        ),
        width="100%",
        spacing="0",
    )


def _onchain_tab() -> rx.Component:
    return rx.vstack(
        _panel(
            "What would happen on-chain",
            rx.text(
                "The twin explains the blockchain layer in plain English: whether the event is just an advisory signal, "
                "a governance proposal, or an action that would be executable on the deployed contracts.",
                style={"color": PALETTE["text"], "font_size": "12px", "line_height": "1.6"},
            ),
            rx.box(
                rx.text(
                    "CPI becomes a real protocol input here: when inflation changes the indexed accounting path, the mapped on-chain step is a PIU price publication on CohortLedger.",
                    style={"color": PALETTE["muted"], "font_size": "11px", "line_height": "1.6", "margin_top": "10px"},
                ),
                style={"padding": "10px 12px", "border": f"1px solid {PALETTE['edge']}", "border_radius": "10px", "margin_top": "10px", "background": "rgba(15, 23, 42, 0.42)"},
            ),
            rx.cond(
                AppState.twin_v2_onchain_rows.length() > 0,
                rx.box(
                    simple_table(
                        [
                            ("year", "Year"),
                            ("simulation", "Simulation event"),
                            ("classification_label", "Would it trigger?"),
                            ("contract_action", "Contract / action"),
                            ("detail", "Explanation"),
                        ],
                        AppState.twin_v2_onchain_rows,
                    ),
                    style={"overflow_x": "auto", "margin_top": "10px"},
                ),
                _empty("On-chain mapping appears after a run."),
            ),
            subtitle="This keeps the protocol story understandable without assuming smart-contract knowledge.",
        ),
        rx.hstack(
            _panel(
                "Model assumptions",
                rx.box(simple_table([("note", "Assumption")], AppState.twin_v2_assumption_rows), style={"overflow_x": "auto"}),
            ),
            _panel(
                "What is simulated at each level",
                rx.box(simple_table([("scope", "Level"), ("detail", "What is simulated")], AppState.twin_v2_model_scope_rows), style={"overflow_x": "auto"}),
            ),
            spacing="3",
            width="100%",
            align="stretch",
        ),
        width="100%",
        spacing="0",
    )


def twin_v2_page() -> rx.Component:
    return shell(
        "Digital Twin",
        "Build a synthetic pension society, run it forward through time, and inspect how population shifts, fund dynamics, fairness, governance, and on-chain actions interact.",
        rx.hstack(
            _control_panel(),
            rx.box(
                _summary_strip(),
                _run_summary_panel(),
                rx.tabs.root(
                    rx.tabs.list(
                        rx.tabs.trigger("Population", value="population"),
                        rx.tabs.trigger("Fund", value="fund"),
                        rx.tabs.trigger("Fairness", value="fairness"),
                        rx.tabs.trigger("Events", value="events"),
                        rx.tabs.trigger("Representative stories", value="stories"),
                        rx.tabs.trigger("On-chain mapping", value="chain"),
                    ),
                    rx.tabs.content(_population_tab(), value="population", style={"padding_top": "12px"}),
                    rx.tabs.content(_fund_tab(), value="fund", style={"padding_top": "12px"}),
                    rx.tabs.content(_fairness_tab(), value="fairness", style={"padding_top": "12px"}),
                    rx.tabs.content(_events_tab(), value="events", style={"padding_top": "12px"}),
                    rx.tabs.content(_stories_tab(), value="stories", style={"padding_top": "12px"}),
                    rx.tabs.content(_onchain_tab(), value="chain", style={"padding_top": "12px"}),
                    default_value="population",
                    width="100%",
                ),
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
