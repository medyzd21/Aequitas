"""Aequitas Reflex app entry.

Wires the product pages to their routes and attaches AppState.refresh_view as
the on_load handler so state stays fresh when the user navigates. The Python
engine remains the source of truth; this module only composes the product
surfaces and sets theme defaults.
"""
from __future__ import annotations

from pathlib import Path

import reflex as rx

from .pages.actions import actions_page
from .pages.contracts import contracts_page
from .pages.fairness import fairness_page
from .pages.how_it_works import how_page
from .pages.investments import investments_page
from .pages.members import members_page
from .pages.operations import operations_page
from .pages.overview import overview_page
from .pages.sandbox import sandbox_page
from .pages.twin_v2 import twin_v2_page
from .state import AppState
from .theme import APP_STYLE, PALETTE


_WALLET_BRIDGE_SOURCE = (
    Path(__file__).resolve().parent / "assets" / "wallet_bridge.js"
).read_text(encoding="utf-8")


app = rx.App(
    style=APP_STYLE,
    theme=rx.theme(
        appearance="dark",
        accent_color="cyan",
        gray_color="slate",
        radius="medium",
        scaling="95%",
    ),
    stylesheets=[
        "https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap",
    ],
    # Inline the browser-side wallet bridge so wallet connection does not
    # depend on a separately-served asset path being available.
    head_components=[
        rx.script(_WALLET_BRIDGE_SOURCE),
    ],
)

# Routes
app.add_page(
    overview_page,
    route="/",
    title="Aequitas · Pension Intelligence",
    description="Digital Twin first, protocol Sandbox second, with live proof on Sepolia.",
    on_load=AppState.refresh_view,
)
app.add_page(
    members_page,
    route="/members",
    title="Aequitas · Members & cohorts",
    description="Member register, per-member valuation and drill-down.",
    on_load=AppState.refresh_view,
)
app.add_page(
    fairness_page,
    route="/fairness",
    title="Aequitas · Fairness & governance",
    description="Corridor test and governance sandbox.",
    on_load=AppState.refresh_view,
)
app.add_page(
    operations_page,
    route="/operations",
    title="Aequitas · Operations",
    description="Human-readable event feed and audit chain.",
    on_load=AppState.refresh_view,
)
app.add_page(
    contracts_page,
    route="/contracts",
    title="Aequitas · On-chain surface",
    description="Deployed contracts and bridged action payloads.",
    on_load=AppState.refresh_view,
)
app.add_page(
    how_page,
    route="/how",
    title="Aequitas · How it works",
    description="Protocol lifecycle and contract interaction map.",
    on_load=AppState.refresh_view,
)
app.add_page(
    twin_v2_page,
    route="/twin",
    title="Aequitas · Digital Twin",
    description="Interactive pension society simulator with event-driven "
                "fund, fairness, governance, and on-chain mapping views.",
    on_load=AppState.refresh_view,
)
app.add_page(
    sandbox_page,
    route="/sandbox",
    title="Aequitas · Sandbox",
    description="Small deterministic protocol lab for explainability and on-chain verification.",
    on_load=AppState.refresh_view,
)
app.add_page(
    investments_page,
    route="/investments",
    title="Aequitas · Investment governance",
    description="Member voting on predefined model portfolios with capped concave weights and publishable on-chain ballot outcomes.",
    on_load=AppState.refresh_view,
)
app.add_page(
    actions_page,
    route="/actions",
    title="Aequitas · Operator Action Center",
    description="Run the protocol in plain English — wallet-signed on "
                "Sepolia or bridged to a terminal command.",
    on_load=AppState.refresh_view,
)
