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
        "Shock switches",
        "Advanced controls",
        "What happened in this run?",
        "Population",
        "Fund",
        "Fairness",
        "Events",
        "Representative stories",
        "On-chain mapping",
        "Execution cost",
        "Fund-linked PIU price path",
        "Contribution purchasing power",
        "Indexed liabilities versus assets",
        "Member investment voting",
        "Investment policy through time",
        "What changed after each ballot?",
        "Investment ballots and outcomes",
        "Latest ballot snapshot",
        "Investment-governance publication mapping",
        "Actuarial proof-layer mapping",
        "Mortality learning",
        "Credibility and experience",
        "Should this run stay selective or move to an L2?",
        "Execution-cost preset",
        "Run Digital Twin V2",
    ):
        assert label in page


def test_story_cards_use_direct_state_selection_not_inline_lambda():
    page = _read("reflex_app/aequitas_rx/pages/twin_v2.py")
    assert 'on_click=AppState.change_twin_v2_story_key(row["key"])' in page
    assert "on_click=lambda: AppState.change_twin_v2_story_key" not in page
    assert "Selected story" in page
    assert "Lifecycle checkpoints" in page
    assert "PIU value" in page
