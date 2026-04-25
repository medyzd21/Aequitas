"""Tests for engine.onchain_registry — the Sepolia deployment registry.

The registry is what the Reflex Actions page reads to decide whether a
live deployment exists and how to link into Etherscan. These tests pin
the parse shape so a future edit to sepolia.json schema breaks CI before
it ships a silently-empty UI.

Note: we deliberately avoid pytest-specific fixtures (monkeypatch,
tmp_path) so the suite runs under the minimal pytest shim used in CI.
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import engine.onchain_registry as regmod
from engine.onchain_registry import (
    LOCAL_ANVIL_CHAIN_ID,
    SEPOLIA_CHAIN_ID,
    ContractRecord,
    chain_name,
    etherscan_address,
    etherscan_tx,
    explorer_base_for,
    is_sepolia,
    load_any_deployment,
    load_registry,
    short_address,
)


ADDR = "0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb4"
TX   = "0xabcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789"


# ---------------------------------------------------------------------------
# Network constants
# ---------------------------------------------------------------------------

def test_sepolia_chain_id_is_pinned():
    assert SEPOLIA_CHAIN_ID == 11155111


def test_is_sepolia_true_only_for_sepolia():
    assert is_sepolia(SEPOLIA_CHAIN_ID) is True
    assert is_sepolia(1) is False
    assert is_sepolia(LOCAL_ANVIL_CHAIN_ID) is False
    assert is_sepolia(None) is False


def test_chain_name_lookup_and_fallback():
    assert chain_name(SEPOLIA_CHAIN_ID) == "Sepolia Testnet"
    assert chain_name(1) == "Ethereum Mainnet"
    assert chain_name(LOCAL_ANVIL_CHAIN_ID) == "Anvil (local)"
    # Unknown chain_id must not raise.
    assert "8453" in chain_name(8453)


def test_explorer_base_for_known_and_unknown():
    assert explorer_base_for(SEPOLIA_CHAIN_ID) == "https://sepolia.etherscan.io"
    assert explorer_base_for(1) == "https://etherscan.io"
    assert explorer_base_for(99999999) is None
    assert explorer_base_for(None) is None


# ---------------------------------------------------------------------------
# URL builders
# ---------------------------------------------------------------------------

def test_etherscan_address_builds_correct_url_on_sepolia():
    url = etherscan_address(SEPOLIA_CHAIN_ID, ADDR)
    assert url == f"https://sepolia.etherscan.io/address/{ADDR}"


def test_etherscan_tx_builds_correct_url_on_sepolia():
    url = etherscan_tx(SEPOLIA_CHAIN_ID, TX)
    assert url == f"https://sepolia.etherscan.io/tx/{TX}"


def test_etherscan_builders_return_none_for_unknown_chain():
    assert etherscan_address(99999999, ADDR) is None
    assert etherscan_tx(99999999, TX) is None


def test_etherscan_builders_return_none_for_empty_inputs():
    assert etherscan_address(SEPOLIA_CHAIN_ID, "") is None
    assert etherscan_tx(SEPOLIA_CHAIN_ID, "") is None


def test_short_address_collapses_middle():
    assert short_address(ADDR).startswith("0x742d")
    assert short_address(ADDR).endswith(ADDR[-4:])
    assert "…" in short_address(ADDR)


def test_short_address_passthrough_short_input():
    assert short_address("") == ""
    assert short_address("0xabc") == "0xabc"


# ---------------------------------------------------------------------------
# load_registry — happy path, missing file, malformed
# ---------------------------------------------------------------------------

def _write_registry(body: dict) -> Path:
    # Caller is responsible for removing the tempfile; we use a name-only
    # tempfile so Path() works across invocations in the same test.
    f = tempfile.NamedTemporaryFile(
        mode="w", delete=False, suffix=".json", prefix="sepolia_"
    )
    try:
        json.dump(body, f)
    finally:
        f.close()
    return Path(f.name)


def test_load_registry_missing_file_returns_none():
    missing = Path(tempfile.gettempdir()) / "definitely_does_not_exist_xyz.json"
    if missing.exists():
        missing.unlink()
    assert load_registry(missing) is None


def test_load_registry_empty_file_returns_none():
    with tempfile.NamedTemporaryFile(
        mode="w", delete=False, suffix=".json"
    ) as f:
        f.write("")
        p = Path(f.name)
    try:
        assert load_registry(p) is None
    finally:
        p.unlink()


def test_load_registry_header_only_returns_object_without_contracts():
    p = _write_registry({
        "chain_id": 11155111,
        "chain_name": "Sepolia Testnet",
        "contracts": {},
    })
    try:
        reg = load_registry(p)
        assert reg is not None
        assert reg.chain_id == SEPOLIA_CHAIN_ID
        assert reg.is_present() is False
        assert reg.as_rows() == []
    finally:
        p.unlink()


def test_load_registry_with_contracts():
    p = _write_registry({
        "chain_id": 11155111,
        "chain_name": "Sepolia Testnet",
        "deployer": "0xDeaDbEeF" + "00" * 16,
        "deployed_at": "2026-04-20T10:00:00Z",
        "explorer_base": "https://sepolia.etherscan.io",
        "verified": True,
        "contracts": {
            "FairnessGate": {
                "address": ADDR,
                "tx_hash": TX,
                "verified": True,
            },
            "CohortLedger": ADDR,  # accept bare-string form
        },
    })
    try:
        reg = load_registry(p)
        assert reg is not None
        assert reg.is_present() is True
        assert reg.address_of("FairnessGate") == ADDR
        assert reg.record("FairnessGate").tx_hash == TX
        assert reg.address_of("CohortLedger") == ADDR
        assert reg.record("FairnessGate").verified is True
    finally:
        p.unlink()


def test_load_registry_surfaces_proof_layer_contracts_when_present():
    p = _write_registry({
        "chain_id": 11155111,
        "contracts": {
            "ActuarialMethodRegistry": {"address": ADDR, "verified": True},
            "ActuarialResultRegistry": {"address": "0x1111111111111111111111111111111111111111", "verified": True},
            "ActuarialVerifier": {"address": "0x2222222222222222222222222222222222222222", "verified": False},
        },
    })
    try:
        reg = load_registry(p)
        assert reg is not None
        rows = reg.as_rows()
        names = {row["name"] for row in rows}
        assert "ActuarialMethodRegistry" in names
        assert "ActuarialResultRegistry" in names
        assert "ActuarialVerifier" in names
        method_row = next(row for row in rows if row["name"] == "ActuarialMethodRegistry")
        assert method_row["explorer_url"].endswith(ADDR)
        assert method_row["verified"] == "yes"
    finally:
        p.unlink()


def test_load_any_deployment_uses_local_registry_when_requested_file_exists():
    p = _write_registry({
        "chain_id": LOCAL_ANVIL_CHAIN_ID,
        "chain_name": "Anvil (local)",
        "contracts": {
            "CohortLedger": {"address": ADDR},
        },
    })
    try:
        with patch.object(regmod, "_sepolia_registry_path", return_value=Path("/definitely/missing/sepolia.json")):
            with patch.object(regmod, "_local_registry_path", return_value=p):
                with patch.object(regmod, "load_latest", return_value=None):
                    reg = load_any_deployment()
        assert reg is not None
        assert reg.chain_id == LOCAL_ANVIL_CHAIN_ID
        assert reg.address_of("CohortLedger") == ADDR
    finally:
        p.unlink()


def test_load_registry_rejects_unknown_contract_keys_silently():
    p = _write_registry({
        "chain_id": 11155111,
        "contracts": {
            "SomeUnknownContract": {"address": ADDR},
            "FairnessGate": {"address": ADDR},
        },
    })
    try:
        reg = load_registry(p)
        assert reg is not None
        assert "FairnessGate" in reg.contracts
        assert "SomeUnknownContract" not in reg.contracts
    finally:
        p.unlink()


def test_load_registry_rejects_non_hex_addresses():
    p = _write_registry({
        "chain_id": 11155111,
        "contracts": {
            "FairnessGate": {"address": "not-an-address"},
            "CohortLedger": {"address": ADDR},
        },
    })
    try:
        reg = load_registry(p)
        assert reg is not None
        assert "FairnessGate" not in reg.contracts
        assert "CohortLedger" in reg.contracts
    finally:
        p.unlink()


def test_load_registry_handles_malformed_json():
    with tempfile.NamedTemporaryFile(
        mode="w", delete=False, suffix=".json"
    ) as f:
        f.write("{ this is not valid json")
        p = Path(f.name)
    try:
        assert load_registry(p) is None
    finally:
        p.unlink()


def test_load_registry_address_url_uses_chain_explorer():
    p = _write_registry({
        "chain_id": 11155111,
        "contracts": {"FairnessGate": {"address": ADDR}},
    })
    try:
        reg = load_registry(p)
        assert reg is not None
        url = reg.address_url("FairnessGate")
        assert url == f"https://sepolia.etherscan.io/address/{ADDR}"
    finally:
        p.unlink()


def test_load_registry_as_rows_shape():
    p = _write_registry({
        "chain_id": 11155111,
        "contracts": {
            "FairnessGate": {"address": ADDR, "verified": True},
            "CohortLedger": {"address": ADDR, "verified": False},
        },
    })
    try:
        reg = load_registry(p)
        rows = reg.as_rows()
        required = {"name", "address", "short", "tx_hash",
                    "verified", "explorer_url"}
        assert all(required <= set(r.keys()) for r in rows)
        verified_flags = {r["name"]: r["verified"] for r in rows}
        assert verified_flags["FairnessGate"] == "yes"
        assert verified_flags["CohortLedger"] == "no"
    finally:
        p.unlink()


def test_contract_record_short_address():
    rec = ContractRecord(name="FairnessGate", address=ADDR)
    s = rec.short_address
    assert s.startswith("0x742d")
    assert s.endswith(ADDR[-4:])


# ---------------------------------------------------------------------------
# load_any_deployment — prefers JSON, falls back to latest.txt
# ---------------------------------------------------------------------------

def _with_patched_registry_paths(json_path_factory, legacy_factory):
    """Context-manager-style helper so we can restore modules without pytest."""
    from engine import onchain_registry as mod
    orig_path = mod._sepolia_registry_path
    orig_load_latest = mod.load_latest
    mod._sepolia_registry_path = json_path_factory
    mod.load_latest = legacy_factory
    return orig_path, orig_load_latest


def _restore_registry_paths(orig_path, orig_load_latest):
    from engine import onchain_registry as mod
    mod._sepolia_registry_path = orig_path
    mod.load_latest = orig_load_latest


def test_load_any_deployment_prefers_json_when_populated():
    p = _write_registry({
        "chain_id": 11155111,
        "contracts": {"FairnessGate": {"address": ADDR}},
    })
    orig = _with_patched_registry_paths(lambda: p, lambda: None)
    try:
        reg = load_any_deployment()
        assert reg is not None
        assert reg.chain_id == SEPOLIA_CHAIN_ID
        assert reg.address_of("FairnessGate") == ADDR
    finally:
        _restore_registry_paths(*orig)
        p.unlink()


def test_load_any_deployment_falls_back_to_latest_txt():
    from engine.deployments import Deployment
    legacy = Deployment(
        owner="0xowner0000000000000000000000000000000dead",
        addresses={"FairnessGate": ADDR.lower()},
        source_path="fake/latest.txt",
    )
    nope = Path(tempfile.gettempdir()) / "missing_sepolia_xyz.json"
    if nope.exists():
        nope.unlink()
    orig = _with_patched_registry_paths(lambda: nope, lambda: legacy)
    try:
        reg = load_any_deployment()
        assert reg is not None
        assert reg.chain_id == LOCAL_ANVIL_CHAIN_ID
        assert reg.address_of("FairnessGate") == ADDR.lower()
    finally:
        _restore_registry_paths(*orig)


def test_load_any_deployment_returns_none_when_nothing_exists():
    nope = Path(tempfile.gettempdir()) / "missing_sepolia_xyz2.json"
    if nope.exists():
        nope.unlink()
    orig = _with_patched_registry_paths(lambda: nope, lambda: None)
    try:
        assert load_any_deployment() is None
    finally:
        _restore_registry_paths(*orig)
