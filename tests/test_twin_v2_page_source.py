"""Source-level pinning tests for the Twin V2 route and page."""
from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def _read(rel_path: str) -> str:
    return (REPO_ROOT / rel_path).read_text(encoding="utf-8")


def test_twin_route_points_to_v2_page():
    app_entry = _read("reflex_app/aequitas_rx/aequitas_rx.py")
    assert "from .pages.twin_v2 import twin_v2_page" in app_entry
    assert "twin_v2_page," in app_entry
    assert 'route="/twin"' in app_entry


def test_legacy_twin_file_still_exists_as_fallback():
    legacy = REPO_ROOT / "reflex_app/aequitas_rx/pages/twin.py"
    assert legacy.is_file()
    assert "run_system_simulation" in legacy.read_text(encoding="utf-8")


def test_twin_v2_page_exposes_product_tabs_and_controls():
    page = _read("reflex_app/aequitas_rx/pages/twin_v2.py")
    for label in (
        "Simulation controls",
        "Basic setup",
        "healthy",
        "stress",
        "governance",
        "fragile",
        "Shock switches",
        "Advanced controls",
        "What happened in this run?",
        "Population",
        "Fund",
        "Fairness",
        "Fairness verdict",
        "Overall verdict",
        "Current fairness gap",
        "Intergenerational balance",
        "Stress pass rate",
        "Latest cohort Money’s Worth Ratio",
        "Worst-hit cohorts",
        "Governance trigger",
        "FairnessGate.submitAndEvaluate",
        "Advanced fairness diagnostics",
        "Events",
        "Representative stories",
        "On-chain mapping",
        "Execution cost",
        "Fund-linked PIU price path",
        "Contribution purchasing power",
        "Indexed liabilities versus assets",
        "Calibration diagnostics",
        "Show starting calibration",
        "starting active/retired mix",
        "funded ratio",
        "annuity factor",
        "Latest-year cohort Money’s Worth Ratio",
        "Actuarial parity",
        "MWR = EPV benefits / EPV contributions. Around 1.00 means the cohort receives actuarially fair value.",
        "Fairness status",
        "Member investment voting",
        "Investment policy through time",
        "What changed after each ballot?",
        "Investment ballots and outcomes",
        "Latest ballot snapshot",
        "Investment-governance publication mapping",
        "Actuarial proof-layer mapping",
        "Mortality learning",
        "Credibility and experience",
        "Mortality adjustment vs prior (%)",
        "Indexed liability (£m)",
        "Funded ratio (%)",
        "If members live longer than expected, liabilities rise; if they die earlier, liabilities fall. Aequitas updates the active mortality basis only as credibility builds.",
        "Should this run stay selective or move to an L2?",
        "Main cost driver",
        "Batch",
        "L2",
        "commitment",
        "Architecture recommendation",
        "Execution architecture recommendation",
        "This view is not just gas accounting. It tells us which parts belong on mainnet, which should be batched, and which may need an L2.",
        "Execution-cost preset",
        "Run Digital Twin V2",
    ):
        assert label in page


def test_mortality_impact_charts_do_not_mix_liability_and_percentage_axes():
    page = _read("reflex_app/aequitas_rx/pages/twin_v2.py")
    assert "Liability impact of the active basis" not in page
    assert page.count('rx.recharts.line(data_key="indexed_liability_m"') >= 2
    assert page.count('rx.recharts.line(data_key="funded_ratio_pct"') >= 2
    assert "Shown on its own £m axis" in page
    assert "Shown as a percentage" in page


def test_fairness_tab_prioritizes_verdict_and_moves_abstract_lines_to_advanced():
    page = _read("reflex_app/aequitas_rx/pages/twin_v2.py")
    assert "This answers the jury question first" in page
    assert "who is harmed" in page
    assert "Sorted by lowest latest-year MWR first" in page
    assert "Show abstract time-series diagnostics" in page
    assert "Kept for actuaries and debugging" in page


def test_execution_cost_view_replaces_repeated_stacked_driver_chart():
    page = _read("reflex_app/aequitas_rx/pages/twin_v2.py")
    assert "Which action type drives the bill?" not in page
    assert "Execution strategy by action type" in page
    assert "Show detailed annual stacked breakdown" in page
    assert "Recommended execution strategy" in page
    assert "Aequitas should not blindly post every tiny member cashflow on Ethereum mainnet." in page


def test_story_cards_use_direct_state_selection_not_inline_lambda():
    page = _read("reflex_app/aequitas_rx/pages/twin_v2.py")
    assert 'on_click=AppState.change_twin_v2_story_key(row["key"])' in page
    assert "on_click=lambda: AppState.change_twin_v2_story_key" not in page
    assert "Selected story" in page
    assert "Lifecycle checkpoints" in page
    assert "PIU value" in page
