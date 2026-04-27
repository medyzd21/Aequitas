"""Sandbox-only Sepolia wallet management.

These wallets are *only* used to demonstrate the on-chain protocol on
Sepolia from a small, deterministic Sandbox roster. They are not custody
wallets and never hold real assets.

Storage: ``.aequitas_dev/sandbox_wallets.json`` (gitignored). Keys never
leave that file or this process — the UI only ever sees addresses.

Wallet generation strategy (in priority order):
  1. ``eth_account`` (if installed) — uses ``Account.create()``.
  2. Foundry's ``cast wallet new --json`` — already a project dependency.
  3. Otherwise raise a clear error.

We deliberately avoid pulling in a heavy crypto stack for the Reflex app:
the runner already shells out to ``cast send`` for actual broadcasts, so
``cast`` is a reasonable assumption for the sandbox proof flow.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterable, Mapping


# ----- roster ---------------------------------------------------------------
# Small deterministic roster. Each entry maps to a Sandbox member in the
# off-chain seed. The labels are jury-friendly captions, not real identities.

@dataclass(frozen=True)
class SandboxMemberSpec:
    label: str
    cohort: int       # birth-year cohort (multiple of 5)
    age: int
    role: str         # "near_retiree" | "active" | "young"
    salary: float
    contribution_rate: float


SANDBOX_ROSTER: tuple[SandboxMemberSpec, ...] = (
    SandboxMemberSpec("Sandbox A — near retiree",     1960, 65, "near_retiree", 38_000.0, 0.10),
    SandboxMemberSpec("Sandbox B — late career",      1965, 60, "active",       45_000.0, 0.10),
    SandboxMemberSpec("Sandbox C — mid career",       1970, 55, "active",       52_000.0, 0.10),
    SandboxMemberSpec("Sandbox D — mid career",       1980, 45, "active",       60_000.0, 0.10),
    SandboxMemberSpec("Sandbox E — early career",     1990, 35, "young",        42_000.0, 0.08),
    SandboxMemberSpec("Sandbox F — entry level",      2000, 25, "young",        28_000.0, 0.06),
)


# ----- file paths -----------------------------------------------------------

def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def default_wallet_path() -> Path:
    return _repo_root() / ".aequitas_dev" / "sandbox_wallets.json"


# ----- address validation ---------------------------------------------------

ADDRESS_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")
PRIVATE_KEY_RE = re.compile(r"^0x[0-9a-fA-F]{64}$")


def is_valid_address(addr: str) -> bool:
    return bool(addr) and bool(ADDRESS_RE.match(addr))


def is_valid_private_key(pk: str) -> bool:
    return bool(pk) and bool(PRIVATE_KEY_RE.match(pk))


# ----- log/redaction helpers -----------------------------------------------

def mask_private_key(pk: str) -> str:
    """Render a private key as ``0xabcd…[REDACTED]`` for logs."""
    if not pk:
        return ""
    if len(pk) < 8:
        return "[REDACTED]"
    return f"{pk[:6]}…[REDACTED]"


def mask_secrets_in_text(text: str, secrets: Iterable[str]) -> str:
    out = text
    for s in secrets:
        if s and len(s) > 4:
            out = out.replace(s, "[REDACTED]")
    return out


# ----- wallet generation ----------------------------------------------------

def _generate_with_eth_account() -> tuple[str, str] | None:
    try:
        from eth_account import Account  # type: ignore
    except Exception:
        return None
    acct = Account.create()
    pk = acct.key.hex()
    if not pk.startswith("0x"):
        pk = "0x" + pk
    addr = acct.address
    return pk.lower(), addr


def _generate_with_cast() -> tuple[str, str] | None:
    cast = shutil.which("cast")
    if not cast:
        return None
    try:
        out = subprocess.run(
            [cast, "wallet", "new", "--json"],
            check=True, capture_output=True, text=True, timeout=10,
        )
    except (subprocess.SubprocessError, OSError):
        return None
    try:
        data = json.loads(out.stdout)
    except json.JSONDecodeError:
        return None
    # cast emits either a dict or a list of dicts depending on version.
    entry = data[0] if isinstance(data, list) and data else data
    if not isinstance(entry, dict):
        return None
    addr = str(entry.get("address") or entry.get("Address") or "").strip()
    pk = str(entry.get("private_key") or entry.get("PrivateKey") or "").strip()
    if not is_valid_address(addr) or not is_valid_private_key(pk):
        return None
    return pk.lower(), addr


def generate_wallet() -> tuple[str, str]:
    """Return ``(private_key_hex, address)``.

    Tries ``eth_account`` first, then ``cast``. Raises ``RuntimeError`` if
    neither is available.
    """
    for fn in (_generate_with_eth_account, _generate_with_cast):
        result = fn()
        if result is not None:
            return result
    raise RuntimeError(
        "Cannot generate sandbox wallets: neither eth_account (Python) nor "
        "cast (foundry) is available. Install one, then retry."
    )


# ----- persistence ----------------------------------------------------------

@dataclass(frozen=True)
class SandboxWalletRecord:
    label: str
    cohort: int
    age: int
    role: str
    address: str
    private_key: str   # never rendered

    def public_view(self) -> dict[str, str | int]:
        return {
            "label": self.label,
            "cohort": int(self.cohort),
            "age": int(self.age),
            "role": self.role,
            "address": self.address,
        }


def load_wallets(path: str | Path | None = None) -> list[SandboxWalletRecord]:
    p = Path(path) if path is not None else default_wallet_path()
    if not p.is_file():
        return []
    try:
        raw = json.loads(p.read_text() or "{}")
    except (json.JSONDecodeError, OSError):
        return []
    wallets = raw.get("wallets") if isinstance(raw, dict) else None
    if not isinstance(wallets, list):
        return []
    out: list[SandboxWalletRecord] = []
    for entry in wallets:
        if not isinstance(entry, dict):
            continue
        addr = str(entry.get("address") or "").strip()
        pk = str(entry.get("private_key") or "").strip()
        if not is_valid_address(addr) or not is_valid_private_key(pk):
            continue
        out.append(SandboxWalletRecord(
            label=str(entry.get("label") or ""),
            cohort=int(entry.get("cohort") or 0),
            age=int(entry.get("age") or 0),
            role=str(entry.get("role") or ""),
            address=addr,
            private_key=pk,
        ))
    return out


def save_wallets(records: Iterable[SandboxWalletRecord], path: str | Path | None = None) -> Path:
    p = Path(path) if path is not None else default_wallet_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "warning": "Sepolia demo wallets only. Not production custody.",
        "wallets": [asdict(r) for r in records],
    }
    p.write_text(json.dumps(payload, indent=2))
    try:
        os.chmod(p, 0o600)
    except OSError:
        pass
    return p


def ensure_wallets(
    roster: Iterable[SandboxMemberSpec] = SANDBOX_ROSTER,
    path: str | Path | None = None,
    generator=generate_wallet,
) -> list[SandboxWalletRecord]:
    """Load existing wallets or generate-and-save matching the roster.

    Generates one wallet per roster entry not yet covered. Existing entries
    keyed by ``label`` are preserved so addresses stay stable across runs.
    """
    p = Path(path) if path is not None else default_wallet_path()
    existing = {r.label: r for r in load_wallets(p)}
    out: list[SandboxWalletRecord] = []
    changed = False
    for spec in roster:
        if spec.label in existing:
            out.append(existing[spec.label])
            continue
        pk, addr = generator()
        out.append(SandboxWalletRecord(
            label=spec.label, cohort=spec.cohort, age=spec.age, role=spec.role,
            address=addr, private_key=pk,
        ))
        changed = True
    if changed or not p.is_file():
        save_wallets(out, p)
    return out


def public_rows(records: Iterable[SandboxWalletRecord]) -> list[dict]:
    """Address-only view safe for the UI / logs."""
    return [r.public_view() for r in records]


__all__ = [
    "SandboxMemberSpec",
    "SANDBOX_ROSTER",
    "SandboxWalletRecord",
    "default_wallet_path",
    "is_valid_address",
    "is_valid_private_key",
    "mask_private_key",
    "mask_secrets_in_text",
    "generate_wallet",
    "load_wallets",
    "save_wallets",
    "ensure_wallets",
    "public_rows",
]
