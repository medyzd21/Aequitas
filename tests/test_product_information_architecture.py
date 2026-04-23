"""Source-level tests for the product narrative refactor."""
from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def _read(rel_path: str) -> str:
    return (REPO_ROOT / rel_path).read_text(encoding="utf-8")


def test_navbar_uses_new_product_structure():
    src = _read("reflex_app/aequitas_rx/components.py")
    for label in (
        'Overview',
        'Digital Twin',
        'Sandbox',
        'Actions',
        'Operations',
        'Contracts / Proof',
        'How It Works',
    ):
        assert f'_nav_link("{label}"' in src
    assert '_nav_link("Members"' not in src
    assert '_nav_link("Fairness"' not in src


def test_app_routes_include_sandbox_but_keep_twin_as_flagship():
    src = _read("reflex_app/aequitas_rx/aequitas_rx.py")
    assert "from .pages.sandbox import sandbox_page" in src
    assert 'route="/sandbox"' in src
    assert 'route="/twin"' in src
    assert "Digital Twin first, protocol Sandbox second" in src


def test_overview_page_is_a_product_homepage_not_old_fund_overview():
    src = _read("reflex_app/aequitas_rx/pages/overview.py")
    for phrase in (
        "Pension intelligence, backed by proof",
        "Flagship experience",
        "Digital Twin",
        "Sandbox",
        "Recommended jury flow",
        "What the chain proves",
    ):
        assert phrase in src
    assert "Fund overview" not in src


def test_sandbox_page_reframes_deterministic_scheme_as_proof_lab():
    src = _read("reflex_app/aequitas_rx/pages/sandbox.py")
    for phrase in (
        "Small deterministic protocol lab",
        "The Sandbox is the proof layer.",
        "PIU and CPI in the sandbox",
        "Mortality learning in the sandbox",
        "CPI and PIU price path",
        "PIU price payload",
        "On-chain verifiable sandbox flow",
        "Scheme",
        "Members",
        "Fairness",
        "On-chain proof",
    ):
        assert phrase in src


def test_contracts_page_reads_as_trust_center():
    src = _read("reflex_app/aequitas_rx/pages/contracts.py")
    for phrase in (
        "Trust center",
        "How CPI reaches the protocol",
        "How mortality learning reaches the protocol",
        "What is deployed?",
        "What can the jury verify?",
        "Recent on-chain evidence",
        "How to confirm trust quickly",
    ):
        assert phrase in src


def test_actions_page_uses_new_product_context_callout():
    src = _read("reflex_app/aequitas_rx/pages/actions.py")
    assert "LIVE SEPOLIA ACTIONS" in src
    assert "Open Sandbox" in src
    assert "Publish CPI-linked PIU price" in src
    assert "Publish mortality basis snapshot" in src
    assert "demo_disclaimer()" not in src
