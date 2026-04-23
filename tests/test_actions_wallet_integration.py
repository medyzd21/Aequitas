"""Source-level pinning tests for the wallet bridge and Actions page.

These tests avoid importing Reflex so they still run under the minimal
Python environment described in the handoff. They pin the integration
contract that matters for the jury flow: the wallet bridge is inlined
into the app, `/actions` no longer shows duplicate deployment messaging,
and tx confirmations are wired back into the UI.
"""
from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def _read(rel_path: str) -> str:
    return (REPO_ROOT / rel_path).read_text(encoding="utf-8")


def test_wallet_bridge_is_inlined_from_source_file():
    app_entry = _read("reflex_app/aequitas_rx/aequitas_rx.py")
    bridge = _read("reflex_app/aequitas_rx/assets/wallet_bridge.js")
    assert "_WALLET_BRIDGE_SOURCE" in app_entry
    assert "rx.script(_WALLET_BRIDGE_SOURCE)" in app_entry
    assert "window.aequitasWallet" in bridge


def test_wallet_bridge_pins_metamask_and_emits_tx_confirmation():
    bridge = _read("reflex_app/aequitas_rx/assets/wallet_bridge.js")
    assert "setTimeout(_pickProvider, 150);" in bridge
    assert "forceMetaMask" in bridge
    assert 'new CustomEvent("aequitas:tx"' in bridge
    assert "window.__aequitasLastConfirmedTx = tx.hash;" in bridge


def test_actions_page_has_single_deployment_signal_and_start_here_copy():
    actions_page = _read("reflex_app/aequitas_rx/pages/actions.py")
    assert "deployment_ribbon()" not in actions_page
    assert "Start by connecting your wallet" in actions_page
    assert "OFF-CHAIN" in actions_page
    assert "LIVE ON SEPOLIA" in actions_page


def test_wallet_components_use_nontechnical_labels_and_tx_bridge():
    components_wallet = _read("reflex_app/aequitas_rx/components_wallet.py")
    state_py = _read("reflex_app/aequitas_rx/state.py")
    assert "BRIDGED · CLI" not in components_wallet
    assert "LIVE · ON-CHAIN" not in components_wallet
    assert "__aequitas_tx_confirmed" in components_wallet
    assert "refresh_tx_confirmation" in state_py
    assert "def on_tx_confirmed" in state_py


def test_publish_piu_price_is_a_live_wallet_action():
    bridge = _read("reflex_app/aequitas_rx/assets/wallet_bridge.js")
    state_py = _read("reflex_app/aequitas_rx/state.py")
    actions_page = _read("reflex_app/aequitas_rx/pages/actions.py")
    assert "function setPiuPrice(uint256 newPrice)" in bridge
    assert "function publishBasis(" in bridge
    assert '"publish_piu_price"' in state_py
    assert '"publish_mortality_basis"' in state_py
    assert "Publish CPI-linked PIU price" in actions_page
    assert "Publish mortality basis snapshot" in actions_page
