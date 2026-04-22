"""Aequitas Reflex app entry.

Wires the six pages to their routes and attaches AppState.refresh_view as the
on_load handler so state is refreshed when the user navigates. The Python
actuarial engine stays the source of truth — this module only composes
pages and sets theme defaults.
"""
from __future__ import annotations

from pathlib import Path

import reflex as rx

from .pages.actions import actions_page
from .pages.contracts import contracts_page
from .pages.fairness import fairness_page
from .pages.how_it_works import how_page
from .pages.members import members_page
from .pages.operations import operations_page
from .pages.overview import overview_page
from .pages.twin import twin_page
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
    title="Aequitas · Fund overview",
    description="Aggregate fund health and cohort signals.",
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
    twin_page,
    route="/twin",
    title="Aequitas · Digital Twin",
    description="Time-evolving synthetic scheme — population, fund, and "
                "fairness through years.",
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
