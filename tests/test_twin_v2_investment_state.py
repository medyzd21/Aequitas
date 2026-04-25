"""Regression checks for Twin V2 investment-governance state wiring."""
from __future__ import annotations

import pytest

pytest.importorskip("reflex")

from reflex_app.aequitas_rx.state import AppState


def test_twin_v2_state_serializes_investment_governance_outputs():
    state = AppState()
    state.twin_v2_population_size = 2_000
    state.twin_v2_horizon_years = 8
    state.twin_v2_seed = 11
    state.twin_v2_investment_voting_enabled = True
    state.twin_v2_investment_ballot_interval_years = 2

    state.run_twin_v2_simulation()

    assert state.twin_v2_investment_summary_text
    assert state.twin_v2_investment_ballot_count >= 1
    assert state.twin_v2_active_policy_name
    assert state.twin_v2_investment_ballot_rows
    assert state.twin_v2_investment_policy_rows
    assert state.twin_v2_investment_onchain_rows
    assert isinstance(state.twin_v2_investment_vote_snapshot_rows, list)
