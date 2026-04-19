"""Tests for the `engine.deployments` loader."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

from engine.deployments import CONTRACT_KEYS, load_latest


def test_returns_none_when_file_missing(tmp_path_factory=None):
    # tmp path is supplied by either pytest fixture or we make one
    with tempfile.TemporaryDirectory() as tmp:
        missing = Path(tmp) / "does-not-exist.txt"
        assert load_latest(missing) is None


def test_parses_well_formed_file():
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "latest.txt"
        p.write_text(
            "owner=0xABCDEF0000000000000000000000000000000001\n"
            "CohortLedger=0x1111111111111111111111111111111111111111\n"
            "FairnessGate=0x2222222222222222222222222222222222222222\n"
            "unknown_key=ignored_value\n"
        )
        dep = load_latest(p)
        assert dep is not None
        assert dep.owner == "0xabcdef0000000000000000000000000000000001"
        assert dep["CohortLedger"] == "0x1111111111111111111111111111111111111111"
        assert dep["FairnessGate"] == "0x2222222222222222222222222222222222222222"
        # unknown keys are ignored, not added
        assert "unknown_key" not in dep.addresses


def test_handles_blank_and_malformed_lines():
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "latest.txt"
        p.write_text(
            "\n"
            "=novaluekey\n"
            "garbage_no_eq\n"
            "CohortLedger=0x3333333333333333333333333333333333333333\n"
        )
        dep = load_latest(p)
        assert dep is not None
        assert dep["CohortLedger"].endswith("3333")


def test_contract_keys_match_deploy_script():
    """Sanity: every key the deploy script writes must be listed here."""
    # Deploy.s.sol writes exactly these, in this order.
    expected = (
        "CohortLedger", "FairnessGate", "MortalityOracle", "LongevaPool",
        "BenefitStreamer", "VestaRouter", "StressOracle", "BackstopVault",
    )
    assert set(expected) == set(CONTRACT_KEYS)
