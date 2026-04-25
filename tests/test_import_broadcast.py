"""Tests for scripts/import_broadcast.py — the Foundry→registry helper.

The helper is what converts `forge script --broadcast` output into
`contracts/deployments/sepolia.json`, which the Reflex app reads.
These tests pin the parse shape so a future Foundry bump doesn't
silently land a broken registry on `main`.

Written against the minimal pytest shim (no fixtures); the helpers
build and tear down tempfiles manually.
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

# Make the scripts/ dir importable without pytest's rootdir magic.
_REPO_ROOT = Path(__file__).resolve().parents[1]
_SCRIPTS = _REPO_ROOT / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import import_broadcast as ib  # noqa: E402  (path hack above)


# ---------------------------------------------------------------------------
# Canned Foundry broadcast log — shrunk to the fields the helper reads.
# ---------------------------------------------------------------------------

def _canned_broadcast() -> dict:
    return {
        "transactions": [
            {
                "transactionType": "CREATE",
                "contractName":    "CohortLedger",
                "contractAddress": "0x4948cbce1c80f166aab30017bd31825da81e09dc",
                "hash":            "0xaaaa000000000000000000000000000000000000000000000000000000000001",
                "transaction": {"from": "0xa275c7e279fb51f419db50244eba5f0f0197e9e0"},
            },
            {
                "transactionType": "CREATE",
                "contractName":    "FairnessGate",
                "contractAddress": "0x334cacf2e0d8cf2c68e96d66d87f21ecb6e13f75",
                "hash":            "0xaaaa000000000000000000000000000000000000000000000000000000000002",
                "transaction": {"from": "0xa275c7e279fb51f419db50244eba5f0f0197e9e0"},
            },
            {
                "transactionType": "CREATE",
                "contractName":    "MortalityOracle",
                "contractAddress": "0xd75cd2f76fd51c6a091b98ebb9bb07f4323dd2fd",
                "hash":            "0xaaaa000000000000000000000000000000000000000000000000000000000003",
                "transaction": {"from": "0xa275c7e279fb51f419db50244eba5f0f0197e9e0"},
            },
            {
                "transactionType": "CREATE",
                "contractName":    "MortalityBasisOracle",
                "contractAddress": "0x8c5d0a5c47d1bf27eb3fb0d7b8df44c0a7497711",
                "hash":            "0xaaaa000000000000000000000000000000000000000000000000000000000003",
                "transaction": {"from": "0xa275c7e279fb51f419db50244eba5f0f0197e9e0"},
            },
            {
                "transactionType": "CREATE",
                "contractName":    "InvestmentPolicyBallot",
                "contractAddress": "0x61bc4aa4f17e64f4da95f12cf092f2cb72a7fb12",
                "hash":            "0xaaaa000000000000000000000000000000000000000000000000000000000003",
                "transaction": {"from": "0xa275c7e279fb51f419db50244eba5f0f0197e9e0"},
            },
            {
                "transactionType": "CREATE",
                "contractName":    "ActuarialMethodRegistry",
                "contractAddress": "0x51bc4aa4f17e64f4da95f12cf092f2cb72a7fb12",
                "hash":            "0xaaaa00000000000000000000000000000000000000000000000000000000000a",
                "transaction": {"from": "0xa275c7e279fb51f419db50244eba5f0f0197e9e0"},
            },
            {
                "transactionType": "CREATE",
                "contractName":    "ActuarialResultRegistry",
                "contractAddress": "0x41bc4aa4f17e64f4da95f12cf092f2cb72a7fb12",
                "hash":            "0xaaaa00000000000000000000000000000000000000000000000000000000000b",
                "transaction": {"from": "0xa275c7e279fb51f419db50244eba5f0f0197e9e0"},
            },
            {
                "transactionType": "CREATE",
                "contractName":    "ActuarialVerifier",
                "contractAddress": "0x31bc4aa4f17e64f4da95f12cf092f2cb72a7fb12",
                "hash":            "0xaaaa00000000000000000000000000000000000000000000000000000000000c",
                "transaction": {"from": "0xa275c7e279fb51f419db50244eba5f0f0197e9e0"},
            },
            {
                "transactionType": "CREATE",
                "contractName":    "LongevaPool",
                "contractAddress": "0x3fa350a007b641c8f2d1cc4c29a41d9999f19a71",
                "hash":            "0xaaaa000000000000000000000000000000000000000000000000000000000004",
                "transaction": {"from": "0xa275c7e279fb51f419db50244eba5f0f0197e9e0"},
            },
            {
                "transactionType": "CREATE",
                "contractName":    "BenefitStreamer",
                "contractAddress": "0x0c58b0f69cb3a9e9ec61810951c905400e768e8b",
                "hash":            "0xaaaa000000000000000000000000000000000000000000000000000000000005",
                "transaction": {"from": "0xa275c7e279fb51f419db50244eba5f0f0197e9e0"},
            },
            {
                "transactionType": "CREATE",
                "contractName":    "VestaRouter",
                "contractAddress": "0x0de6addf833d1af1650ba6a9e7c10e76ec7c3a19",
                "hash":            "0xaaaa000000000000000000000000000000000000000000000000000000000006",
                "transaction": {"from": "0xa275c7e279fb51f419db50244eba5f0f0197e9e0"},
            },
            {
                "transactionType": "CREATE",
                "contractName":    "StressOracle",
                "contractAddress": "0x4d3e155d4243e372917344968fd3907a0462c5c7",
                "hash":            "0xaaaa000000000000000000000000000000000000000000000000000000000007",
                "transaction": {"from": "0xa275c7e279fb51f419db50244eba5f0f0197e9e0"},
            },
            {
                "transactionType": "CREATE",
                "contractName":    "BackstopVault",
                "contractAddress": "0x6a34eaa0e10a449671e125873d2036aa989ae826",
                "hash":            "0xaaaa000000000000000000000000000000000000000000000000000000000008",
                "transaction": {"from": "0xa275c7e279fb51f419db50244eba5f0f0197e9e0"},
            },
            # An unknown CREATE that MUST be ignored by the helper.
            {
                "transactionType": "CREATE",
                "contractName":    "RandomProxy",
                "contractAddress": "0xdeadbeef0000000000000000000000000000dead",
                "hash":            "0xbbbb000000000000000000000000000000000000000000000000000000000009",
                "transaction": {"from": "0xa275c7e279fb51f419db50244eba5f0f0197e9e0"},
            },
        ],
        "timestamp": 1776807180756,   # milliseconds since epoch
        "chain":     11155111,
    }


# ---------------------------------------------------------------------------
# Extraction helpers
# ---------------------------------------------------------------------------

def test_extract_create_transactions_filters_unknown():
    rows = ib.extract_create_transactions(_canned_broadcast())
    names = [r["name"] for r in rows]
    assert "RandomProxy" not in names
    assert set(names) == ib.ALLOWED_CONTRACTS
    # All canonical contracts must be present.
    assert len(rows) == len(ib.ALLOWED_CONTRACTS)


def test_extract_create_transactions_returns_empty_when_no_creates():
    broadcast = {"transactions": [
        {"transactionType": "CALL", "contractName": "X",
         "contractAddress": "0x1", "hash": "0x1"},
    ]}
    assert ib.extract_create_transactions(broadcast) == []


def test_infer_deployer_pulls_from_first_create():
    deployer = ib.infer_deployer(_canned_broadcast())
    assert deployer.lower() == "0xa275c7e279fb51f419db50244eba5f0f0197e9e0"


def test_infer_deployer_returns_empty_when_missing():
    broadcast = {"transactions": []}
    assert ib.infer_deployer(broadcast) == ""


def test_infer_deployed_at_parses_milliseconds():
    # 1776807180756 ms = 2026-04-21 around 21:33 UTC
    iso = ib.infer_deployed_at(_canned_broadcast())
    assert iso.startswith("2026-04-")
    assert iso.endswith("Z")
    assert "T" in iso


def test_infer_deployed_at_parses_seconds():
    broadcast = {"timestamp": 1_700_000_000}   # 2023-11-14 ~UTC
    iso = ib.infer_deployed_at(broadcast)
    assert iso.startswith("2023-11-")


def test_infer_deployed_at_empty_when_absent():
    assert ib.infer_deployed_at({}) == ""
    assert ib.infer_deployed_at({"timestamp": "not-a-number"}) == ""


# ---------------------------------------------------------------------------
# build_registry — the whole-shape output
# ---------------------------------------------------------------------------

def test_build_registry_shape():
    payload = ib.build_registry(_canned_broadcast())
    assert payload["chain_id"] == 11155111
    assert payload["chain_name"] == "Sepolia Testnet"
    assert payload["explorer_base"] == ib.SEPOLIA_EXPLORER
    # All canonical contract rows.
    assert set(payload["contracts"].keys()) == ib.ALLOWED_CONTRACTS
    # No contract is verified by default.
    assert all(not c["verified"] for c in payload["contracts"].values())
    # The overall verified flag should be False when no verified set.
    assert payload["verified"] is False


def test_build_registry_with_verified_all_flags_all_contracts():
    payload = ib.build_registry(
        _canned_broadcast(),
        verified=ib.ALLOWED_CONTRACTS,
    )
    assert payload["verified"] is True
    assert all(c["verified"] for c in payload["contracts"].values())


def test_build_registry_rejects_empty_broadcast():
    raised = False
    try:
        ib.build_registry({"transactions": []})
    except ValueError:
        raised = True
    assert raised, "build_registry should raise on empty broadcast"


def test_build_registry_preserves_existing_metadata():
    existing = {
        "$schema":  "./sepolia.schema.md",
        "rpc_hint": "https://sepolia.infura.io/v3/<project>",
        "notes":    "User-authored note that must survive.",
        "chain_id": 11155111,
        "contracts": {},
    }
    payload = ib.build_registry(_canned_broadcast(), existing=existing)
    assert payload["$schema"] == "./sepolia.schema.md"
    assert payload["rpc_hint"].startswith("https://sepolia.infura.io/")
    assert payload["notes"] == "User-authored note that must survive."
    # But the regenerated block replaces stale top-level fields.
    assert len(payload["contracts"]) == len(ib.ALLOWED_CONTRACTS)


# ---------------------------------------------------------------------------
# _parse_verified_arg — CLI normalisation
# ---------------------------------------------------------------------------

def test_parse_verified_arg_empty():
    assert ib._parse_verified_arg(None, ["A", "B"]) == set()
    assert ib._parse_verified_arg("", ["A", "B"]) == set()
    assert ib._parse_verified_arg(False, ["A", "B"]) == set()


def test_parse_verified_arg_all():
    assert ib._parse_verified_arg("all", ["A", "B"]) == {"A", "B"}
    assert ib._parse_verified_arg(True, ["A", "B"]) == {"A", "B"}


def test_parse_verified_arg_comma_list_filters_unknown():
    assert ib._parse_verified_arg("A,Nope,B", ["A", "B"]) == {"A", "B"}


# ---------------------------------------------------------------------------
# Round-trip via tempfiles
# ---------------------------------------------------------------------------

def test_write_registry_roundtrip_on_disk():
    with tempfile.TemporaryDirectory() as tmp:
        reg_path = Path(tmp) / "sepolia.json"
        payload = ib.build_registry(
            _canned_broadcast(),
            verified=ib.ALLOWED_CONTRACTS,
        )
        ib.write_registry(reg_path, payload)
        reloaded = json.loads(reg_path.read_text(encoding="utf-8"))
        assert reloaded["chain_id"] == 11155111
        assert len(reloaded["contracts"]) == len(ib.ALLOWED_CONTRACTS)
        # Addresses preserved verbatim (lowercase, as written by Foundry).
        assert reloaded["contracts"]["CohortLedger"]["address"].startswith("0x4948")


def test_cli_dry_run_prints_registry(capsys=None):
    """End-to-end: run the CLI with --dry-run and parse the stdout."""
    with tempfile.TemporaryDirectory() as tmp:
        bc_path = Path(tmp) / "run-latest.json"
        bc_path.write_text(json.dumps(_canned_broadcast()), encoding="utf-8")

        # Redirect stdout manually because the minimal pytest shim has no
        # `capsys` fixture.
        import io
        import contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = ib._main([str(bc_path), str(Path(tmp) / "out.json"),
                           "--dry-run", "--verified", "all"])
        assert rc == 0
        parsed = json.loads(buf.getvalue())
        assert parsed["chain_id"] == 11155111
        assert parsed["verified"] is True
        assert len(parsed["contracts"]) == len(ib.ALLOWED_CONTRACTS)


def test_cli_missing_broadcast_returns_error_code():
    with tempfile.TemporaryDirectory() as tmp:
        missing = Path(tmp) / "does-not-exist.json"
        import io
        import contextlib
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            rc = ib._main([str(missing), str(Path(tmp) / "out.json")])
        assert rc == 2


def test_downstream_registry_loads_via_engine_onchain_registry():
    """Smoke: the file produced by the helper must round-trip through
    `engine.onchain_registry.load_registry` without losing fields."""
    from engine.onchain_registry import load_registry
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "sepolia.json"
        payload = ib.build_registry(
            _canned_broadcast(),
            verified=ib.ALLOWED_CONTRACTS,
        )
        ib.write_registry(out, payload)
        reg = load_registry(out)
        assert reg is not None
        assert reg.chain_id == 11155111
        assert reg.is_present()
        assert "FairnessGate" in reg.contracts
        assert reg.address_of("FairnessGate").startswith("0x334c")
