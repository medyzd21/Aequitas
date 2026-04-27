"""Tests for the sandbox Sepolia wallet store."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from engine.sandbox_wallets import (
    SANDBOX_ROSTER,
    SandboxWalletRecord,
    ensure_wallets,
    is_valid_address,
    is_valid_private_key,
    load_wallets,
    mask_private_key,
    mask_secrets_in_text,
    public_rows,
    save_wallets,
)


_FAKE_PK = "0x" + "ab" * 32     # 0x + 64 hex
_FAKE_ADDR = "0x" + "cd" * 20   # 0x + 40 hex


def _stub_generator():
    return _FAKE_PK, _FAKE_ADDR


def test_address_and_private_key_validators():
    assert is_valid_address(_FAKE_ADDR)
    assert not is_valid_address("0x123")
    assert is_valid_private_key(_FAKE_PK)
    assert not is_valid_private_key(_FAKE_ADDR)


def test_mask_private_key_never_renders_full_key():
    masked = mask_private_key(_FAKE_PK)
    assert _FAKE_PK not in masked
    assert "[REDACTED]" in masked


def test_mask_secrets_in_text_redacts_values():
    text = f"using {_FAKE_PK} and rpc https://example"
    out = mask_secrets_in_text(text, [_FAKE_PK])
    assert _FAKE_PK not in out
    assert "[REDACTED]" in out


def test_save_and_load_roundtrip(tmp_path: Path):
    p = tmp_path / "wallets.json"
    rec = SandboxWalletRecord(
        label="Sandbox A — near retiree", cohort=1960, age=65, role="near_retiree",
        address=_FAKE_ADDR, private_key=_FAKE_PK,
    )
    save_wallets([rec], p)
    loaded = load_wallets(p)
    assert len(loaded) == 1
    assert loaded[0].address == _FAKE_ADDR
    assert loaded[0].private_key == _FAKE_PK


def test_ensure_wallets_generates_one_per_roster(tmp_path: Path):
    p = tmp_path / "wallets.json"
    counter = {"n": 0}

    def gen():
        counter["n"] += 1
        # produce distinct hex per call so the addresses differ
        n = counter["n"]
        addr = "0x" + f"{n:02x}" + "cd" * 19
        pk = "0x" + f"{n:02x}" + "ab" * 31
        return pk, addr

    records = ensure_wallets(roster=SANDBOX_ROSTER, path=p, generator=gen)
    assert len(records) == len(SANDBOX_ROSTER)
    assert all(is_valid_address(r.address) for r in records)
    assert all(is_valid_private_key(r.private_key) for r in records)
    # idempotent — second call doesn't re-generate
    counter_before = counter["n"]
    again = ensure_wallets(roster=SANDBOX_ROSTER, path=p, generator=gen)
    assert counter["n"] == counter_before
    assert [r.address for r in again] == [r.address for r in records]


def test_public_rows_does_not_expose_private_keys(tmp_path: Path):
    p = tmp_path / "wallets.json"
    rec = SandboxWalletRecord(
        label="Sandbox A — near retiree", cohort=1960, age=65, role="near_retiree",
        address=_FAKE_ADDR, private_key=_FAKE_PK,
    )
    save_wallets([rec], p)
    rows = public_rows(load_wallets(p))
    blob = json.dumps(rows)
    assert _FAKE_PK not in blob
    assert _FAKE_ADDR in blob
