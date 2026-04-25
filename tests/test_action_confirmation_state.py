"""Regression checks for honest off-chain action confirmation state."""
from __future__ import annotations

from unittest.mock import patch

import pytest

pytest.importorskip("reflex")

from reflex_app.aequitas_rx.state import AppState  # noqa: E402


def test_offchain_acknowledgement_does_not_mark_action_confirmed_onchain():
    state = AppState()
    state.confirm_action_key = "publish_mortality_basis"
    state.confirm_action_label = "Publish mortality basis snapshot"
    state.confirm_contract = "MortalityBasisOracle"
    state.confirm_function = "publishBasis"
    state.confirm_is_live = False
    state.confirm_mode_label = "After next Sepolia deployment"
    state.confirm_open = True

    state.confirm_action()

    assert state.last_tx_status == "acknowledged"
    assert state.tx_pill_label == "OFF-CHAIN ONLY"
    assert state.last_tx_hash == ""


def test_auditor_demo_flow_uses_devtools_when_enabled():
    state = AppState()
    state.devtools_enabled = True
    state.confirm_action_key = "demo_flow"
    state.confirm_mode_label = "Developer tool"
    state.confirm_open = True

    def _mark_success(self: AppState) -> None:
        self.devtools_status = "success"
        self.devtools_target = "demo flow"
        self.devtools_message = "demo ok"

    with patch.object(AppState, "run_local_demo_flow", autospec=True, side_effect=_mark_success) as run:
        with patch.object(AppState, "_refresh_events", autospec=True) as refresh_events:
            state.confirm_action()

    run.assert_called_once_with(state)
    assert state.confirm_open is False
    assert state.last_tx_status == "acknowledged"
    assert state.last_tx_hash == ""
    assert state.last_tx_contract == "Developer Tools"
    refresh_events.assert_called()


def test_auditor_devtool_action_fails_clearly_when_disabled():
    state = AppState()
    state.devtools_enabled = False
    state.confirm_action_key = "deploy_protocol"
    state.confirm_mode_label = "Developer tool"
    state.confirm_open = True

    with patch.object(AppState, "_refresh_events", autospec=True):
        state.confirm_action()

    assert state.confirm_open is False
    assert state.last_tx_status == "failed"
    assert "AEQUITAS_DEVTOOLS=1" in state.last_tx_error
