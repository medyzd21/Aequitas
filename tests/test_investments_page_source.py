"""Source-level checks for the investment-governance MVP."""
from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def _read(rel_path: str) -> str:
    return (REPO_ROOT / rel_path).read_text(encoding="utf-8")


def test_investments_page_explains_rule_and_guardrails():
    src = _read("reflex_app/aequitas_rx/pages/investments.py")
    for phrase in (
        "Investment policy sandbox",
        "primary investment-governance story lives inside the Digital Twin",
        "Every member gets one base vote.",
        "5% of the published ballot weight",
        "Model portfolios",
        "Current ballot draft",
        "Validation before publication",
        "What the chain does and does not do",
        "Cast live vote",
    ):
        assert phrase in src


def test_state_wires_investment_payloads_and_vote_action():
    src = _read("reflex_app/aequitas_rx/state.py")
    for phrase in (
        "investment_policy_rows",
        "investment_weight_rows",
        "investment_support_rows",
        "def _refresh_investment_governance",
        "def open_investment_vote_action",
        "encode_create_investment_ballot",
        "encode_investment_ballot_weights",
        "encode_investment_vote",
        "encode_finalize_investment_ballot",
    ):
        assert phrase in src
