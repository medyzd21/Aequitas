"""Shared UI components for the Aequitas Reflex frontend.

Everything that more than one page reuses lives here: the navbar + shell,
the KPI strip, the two ribbons (disclaimer + deployment), pill, and the
generic action card used on the Contracts page.
"""
from __future__ import annotations

import reflex as rx

from .state import AppState
from .theme import (
    CARD_STYLE,
    KPI_TILE_STYLE,
    PALETTE,
    PILL_STYLES,
    RIBBON_STYLE,
)


# --------------------------------------------------------------------------- pill
def pill(label: str, kind: str = "muted") -> rx.Component:
    style = PILL_STYLES.get(kind, PILL_STYLES["muted"])
    return rx.box(
        label,
        style={
            **style,
            "display":         "inline-block",
            "padding":         "2px 8px",
            "border_radius":   "999px",
            "font_size":       "10px",
            "font_weight":     "600",
            "letter_spacing":  "0.04em",
        },
    )


# --------------------------------------------------------------------------- navbar
def _nav_link(label: str, href: str) -> rx.Component:
    return rx.link(
        label,
        href=href,
        style={
            "color":        PALETTE["text"],
            "font_size":    "13px",
            "font_weight": "500",
            "padding":      "6px 12px",
            "border_radius": "6px",
            "text_decoration": "none",
            "_hover": {"background": PALETTE["edge"], "color": PALETTE["accent"]},
        },
    )


def navbar() -> rx.Component:
    # Late import avoids a circular dependency between components.py and
    # components_wallet.py (which imports `pill` from this module).
    from .components_wallet import wallet_badge
    return rx.hstack(
        rx.hstack(
            rx.heading("AEQUITAS",
                       size="4",
                       style={"color": PALETTE["text"], "letter_spacing": "0.15em",
                              "font_weight": "700"}),
            rx.text("· Pension Intelligence",
                    style={"color": PALETTE["muted"], "font_size": "12px"}),
            spacing="3",
            align="center",
        ),
        rx.spacer(),
        rx.hstack(
            _nav_link("Overview", "/"),
            _nav_link("Digital Twin", "/twin"),
            _nav_link("Sandbox", "/sandbox"),
            _nav_link("Actions", "/actions"),
            _nav_link("Operations", "/operations"),
            _nav_link("Contracts / Proof", "/contracts"),
            _nav_link("How It Works", "/how"),
            spacing="1",
        ),
        rx.box(wallet_badge(), style={"margin_left": "12px"}),
        width="100%",
        padding="14px 24px",
        background=PALETTE["panel"],
        border_bottom=f"1px solid {PALETTE['edge']}",
        position="sticky",
        top="0",
        z_index="100",
    )


# --------------------------------------------------------------------------- KPI strip
def _kpi_tile(label: str, value, sub: rx.Component | str = "") -> rx.Component:
    return rx.box(
        rx.text(label,
                style={"color": PALETTE["muted"], "font_size": "10px",
                       "letter_spacing": "0.08em", "text_transform": "uppercase",
                       "margin_bottom": "2px"}),
        rx.text(value,
                style={"color": PALETTE["text"], "font_size": "20px",
                       "font_weight": "600", "line_height": "1.2"}),
        sub if isinstance(sub, rx.Component) else rx.text(
            sub,
            style={"color": PALETTE["muted"], "font_size": "10px",
                   "margin_top": "2px"},
        ),
        style=KPI_TILE_STYLE,
    )


def kpi_strip() -> rx.Component:
    # Pill colouring driven by state.*_pill computed vars
    return rx.box(
        rx.hstack(
            _kpi_tile(
                "Members", AppState.members_count,
                rx.text(f"{AppState.cohorts_count} cohorts",
                        style={"color": PALETTE["muted"], "font_size": "10px"}),
            ),
            _kpi_tile("EPV · Contributions", AppState.epv_c_fmt,
                      "actuarial present value"),
            _kpi_tile("EPV · Benefits", AppState.epv_b_fmt,
                      "liability at valuation date"),
            _kpi_tile(
                "Scheme MWR", AppState.mwr_fmt,
                rx.hstack(
                    rx.match(
                        AppState.mwr_pill,
                        ("good",  pill("HEALTHY", "good")),
                        ("warn",  pill("WATCH", "warn")),
                        ("bad",   pill("STRESS", "bad")),
                        pill("NO DATA", "muted"),
                    ),
                    spacing="2",
                ),
            ),
            _kpi_tile("Funded Ratio", AppState.funded_ratio_fmt,
                      "contrib-to-date / EPV(ben)"),
            _kpi_tile(
                "Gini (MWR)", AppState.gini_fmt,
                rx.match(
                    AppState.gini_pill,
                    ("good",  pill("HEALTHY", "good")),
                    ("warn",  pill("WATCH", "warn")),
                    ("bad",   pill("STRESS", "bad")),
                    pill("NO DATA", "muted"),
                ),
            ),
            _kpi_tile(
                "Intergen Index", AppState.intergen_fmt,
                rx.match(
                    AppState.intergen_pill,
                    ("good",  pill("HEALTHY", "good")),
                    ("warn",  pill("WATCH", "warn")),
                    ("bad",   pill("STRESS", "bad")),
                    pill("NO DATA", "muted"),
                ),
            ),
            _kpi_tile("MWR range", AppState.mwr_range_fmt,
                      "min → max across cohorts"),
            spacing="3",
            width="100%",
            align="stretch",
            wrap="wrap",
        ),
        style={
            **CARD_STYLE,
            # Was sticky — that caused the KPI strip to overlay the
            # contract-topology SVG on the How-It-Works page. The navbar
            # is still sticky, which is enough for orientation.
            "margin_bottom": "10px",
        },
    )


# --------------------------------------------------------------------------- ribbons
def demo_disclaimer() -> rx.Component:
    return rx.box(
        rx.hstack(
            pill("DEMO DATA", "warn"),
            rx.text(
                "This terminal runs on illustrative assumptions and a "
                "small sample scheme. Funded ratio, MWR, Gini, intergen "
                "index and stress figures are synthetic — they demonstrate "
                "the mechanism, not a calibrated real pension scheme.",
                style={"color": PALETTE["muted"], "font_size": "12px"},
            ),
            spacing="3",
            align="center",
        ),
        style={**RIBBON_STYLE,
               "border_left": f"3px solid {PALETTE['warn']}",
               "margin_bottom": "10px"},
    )


def deployment_ribbon() -> rx.Component:
    return rx.cond(
        AppState.deployment_detected,
        rx.box(
            rx.hstack(
                pill("ON-CHAIN CONNECTED", "good"),
                rx.text(
                    f"{AppState.deployment_count} contracts deployed · "
                    f"owner ",
                    style={"color": PALETTE["muted"], "font_size": "12px"},
                ),
                rx.code(AppState.deployment_owner,
                        style={"color": PALETTE["text"], "font_size": "11px"}),
                spacing="3",
                align="center",
            ),
            style={**RIBBON_STYLE, "margin_bottom": "10px"},
        ),
        rx.box(
            rx.hstack(
                pill("OFF-CHAIN ONLY", "muted"),
                rx.text(
                    "No deployment detected — run "
                    "forge script script/Deploy.s.sol --rpc-url localhost "
                    "--broadcast to connect this terminal to a live stack.",
                    style={"color": PALETTE["muted"], "font_size": "12px"},
                ),
                spacing="3",
                align="center",
            ),
            style={**RIBBON_STYLE, "margin_bottom": "10px"},
        ),
    )


# --------------------------------------------------------------------------- shell
def page_header(title: str, subtitle: str) -> rx.Component:
    return rx.box(
        rx.heading(title, size="6",
                   style={"color": PALETTE["text"], "margin_bottom": "4px"}),
        rx.text(subtitle,
                style={"color": PALETTE["muted"], "font_size": "13px"}),
        style={"margin_bottom": "14px", "margin_top": "6px"},
    )


def sidebar_controls() -> rx.Component:
    """Small control block rendered in the left column of some pages."""
    return rx.box(
        rx.heading("Controls", size="3", style={"color": PALETTE["text"]}),
        rx.text("Scheme assumptions",
                style={"color": PALETTE["muted"], "font_size": "11px",
                       "margin_top": "6px", "margin_bottom": "2px"}),
        rx.text("Valuation year",
                style={"color": PALETTE["muted"], "font_size": "11px"}),
        rx.input(
            value=AppState.valuation_year.to_string(),
            on_change=AppState.change_valuation_year,
            type="number",
            size="1",
        ),
        rx.text("Discount rate",
                style={"color": PALETTE["muted"], "font_size": "11px",
                       "margin_top": "6px"}),
        rx.input(
            value=AppState.discount_rate.to_string(),
            on_change=AppState.change_discount_rate,
            type="number",
            step="0.005",
            size="1",
        ),
        rx.text("Investment return",
                style={"color": PALETTE["muted"], "font_size": "11px",
                       "margin_top": "6px"}),
        rx.input(
            value=AppState.investment_return.to_string(),
            on_change=AppState.change_investment_return,
            type="number",
            step="0.005",
            size="1",
        ),
        rx.text("Salary growth",
                style={"color": PALETTE["muted"], "font_size": "11px",
                       "margin_top": "6px"}),
        rx.input(
            value=AppState.salary_growth.to_string(),
            on_change=AppState.change_salary_growth,
            type="number",
            step="0.005",
            size="1",
        ),
        rx.hstack(
            rx.button(
                "Load demo",
                on_click=AppState.load_demo,
                color_scheme="cyan",
                size="1",
                width="100%",
            ),
            rx.button(
                "Reset",
                on_click=AppState.reset_demo,
                variant="soft",
                color_scheme="gray",
                size="1",
                width="100%",
            ),
            width="100%",
            spacing="2",
            margin_top="10px",
        ),
        rx.text(
            f"{AppState.members_count} members",
            style={"color": PALETTE["muted"], "font_size": "11px",
                   "margin_top": "10px"},
        ),
        style={**CARD_STYLE, "width": "220px", "flex_shrink": "0"},
    )


def shell(
    title: str,
    subtitle: str,
    *children,
    show_demo_disclaimer: bool = True,
    show_deployment_ribbon: bool = True,
    show_kpis: bool = True,
) -> rx.Component:
    """Wraps each page with navbar + KPI strip + ribbons + content."""
    return rx.box(
        navbar(),
        rx.box(
            rx.cond(show_demo_disclaimer, demo_disclaimer(), rx.fragment()),
            rx.cond(show_deployment_ribbon, deployment_ribbon(), rx.fragment()),
            rx.cond(show_kpis, kpi_strip(), rx.fragment()),
            page_header(title, subtitle),
            *children,
            style={
                "max_width": "1400px",
                "margin":    "0 auto",
                "padding":   "20px 24px 64px 24px",
            },
        ),
        style={
            "background":  PALETTE["bg"],
            "min_height":  "100vh",
            "color":       PALETTE["text"],
            "font_family": "Inter, system-ui, sans-serif",
        },
    )


# --------------------------------------------------------------------------- action card
def action_card(
    name: str,
    actor: str,
    target: str,
    economic: str,
    actuarial: str,
    payload_body: rx.Component,
) -> rx.Component:
    """Contracts-page card: name + actor → target + two meaning lines + payload expander."""
    return rx.box(
        rx.hstack(
            rx.text(name,
                    style={"color": PALETTE["text"], "font_size": "14px",
                           "font_weight": "600"}),
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
            rx.text.strong("Economic meaning: ",
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
                header=rx.text("Raw bridged payload (technical appendix)",
                               style={"color": PALETTE["muted"], "font_size": "11px"}),
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


# --------------------------------------------------------------------------- generic table
def simple_table(columns: list[tuple[str, str]], rows_var) -> rx.Component:
    """columns is list of (key, label); rows_var is an rx.Var[list[dict]]."""
    return rx.table.root(
        rx.table.header(
            rx.table.row(
                *[rx.table.column_header_cell(label) for _, label in columns]
            )
        ),
        rx.table.body(
            rx.foreach(
                rows_var,
                lambda row: rx.table.row(
                    *[rx.table.cell(row[key]) for key, _ in columns]
                ),
            )
        ),
        width="100%",
    )
