"""On-chain deployment registry — single source of truth for network state.

This module sits on top of the existing `engine.deployments.load_latest()`
helper. Where `load_latest()` parses the tiny `latest.txt` key=value file
that Foundry's Deploy script writes after a local Anvil run, this module
reads a richer JSON registry at `contracts/deployments/sepolia.json`.

The JSON registry is the file the Reflex app should trust in production:

    {
      "chain_id": 11155111,
      "chain_name": "sepolia",
      "deployer": "0x...",
      "deployed_at": "2026-04-20T17:30:00Z",
      "explorer_base": "https://sepolia.etherscan.io",
      "rpc_hint": "https://sepolia.infura.io/v3/<key>",
      "verified": true,
      "contracts": {
        "CohortLedger":    {"address": "0x...", "tx_hash": "0x...", "verified": true},
        "FairnessGate":    {"address": "0x...", "tx_hash": "0x...", "verified": true},
        ...
      }
    }

Design notes:

* Readonly. Nothing in this module writes files — the Foundry deploy
  script does that. The UI just reads and displays.
* Dependency-free. No web3.py, no json-schema library; hand-rolled parsing
  so the Reflex app stays light.
* Graceful: every access path returns `None` / empty rather than raising,
  because the UI is allowed to render "no deployment yet" and still work.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from engine.deployments import CONTRACT_KEYS, Deployment, load_latest


# ---------------------------------------------------------------------------
# Network constants (kept tiny — add more only when the UI grows to them)
# ---------------------------------------------------------------------------

SEPOLIA_CHAIN_ID = 11155111
MAINNET_CHAIN_ID = 1
LOCAL_ANVIL_CHAIN_ID = 31337

KNOWN_CHAINS: dict[int, str] = {
    MAINNET_CHAIN_ID:     "Ethereum Mainnet",
    SEPOLIA_CHAIN_ID:     "Sepolia Testnet",
    LOCAL_ANVIL_CHAIN_ID: "Anvil (local)",
    5:                    "Goerli Testnet",
    17000:                "Holesky Testnet",
}

EXPLORER_BASE: dict[int, str] = {
    MAINNET_CHAIN_ID:     "https://etherscan.io",
    SEPOLIA_CHAIN_ID:     "https://sepolia.etherscan.io",
    5:                    "https://goerli.etherscan.io",
    17000:                "https://holesky.etherscan.io",
}


def chain_name(chain_id: int | None) -> str:
    if chain_id is None:
        return "—"
    return KNOWN_CHAINS.get(int(chain_id), f"chain {chain_id}")


def is_sepolia(chain_id: int | None) -> bool:
    return chain_id is not None and int(chain_id) == SEPOLIA_CHAIN_ID


def explorer_base_for(chain_id: int | None) -> str | None:
    if chain_id is None:
        return None
    return EXPLORER_BASE.get(int(chain_id))


def etherscan_address(chain_id: int | None, address: str) -> str | None:
    """Deep-link to an address page on the relevant Etherscan."""
    base = explorer_base_for(chain_id)
    if not base or not address:
        return None
    return f"{base}/address/{address}"


def etherscan_tx(chain_id: int | None, tx_hash: str) -> str | None:
    """Deep-link to a transaction page on the relevant Etherscan."""
    base = explorer_base_for(chain_id)
    if not base or not tx_hash:
        return None
    return f"{base}/tx/{tx_hash}"


# ---------------------------------------------------------------------------
# Registry dataclass
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ContractRecord:
    name: str
    address: str
    tx_hash: str = ""
    verified: bool = False

    @property
    def short_address(self) -> str:
        a = self.address
        if not a or len(a) < 10:
            return a
        return f"{a[:6]}…{a[-4:]}"


@dataclass(frozen=True)
class OnchainRegistry:
    """Parsed view of sepolia.json (or any chain-specific registry).

    `source_path` is kept so the UI can show *where* the registry came from.
    """
    chain_id: int
    chain_name: str
    deployer: str
    deployed_at: str
    explorer_base: str
    rpc_hint: str
    verified: bool
    contracts: Mapping[str, ContractRecord]
    source_path: str
    raw: Mapping[str, Any] = field(default_factory=dict)

    # ------------------------------------------------------------------
    def address_of(self, contract_name: str) -> str | None:
        rec = self.contracts.get(contract_name)
        return rec.address if rec else None

    def record(self, contract_name: str) -> ContractRecord | None:
        return self.contracts.get(contract_name)

    def is_present(self) -> bool:
        return bool(self.contracts)

    def address_url(self, contract_name: str) -> str | None:
        rec = self.contracts.get(contract_name)
        if not rec:
            return None
        return etherscan_address(self.chain_id, rec.address)

    def as_rows(self) -> list[dict]:
        """Table-friendly rows for the Reflex UI."""
        rows = []
        for key in CONTRACT_KEYS:
            rec = self.contracts.get(key)
            if not rec:
                continue
            rows.append({
                "name":         rec.name,
                "address":      rec.address,
                "short":        rec.short_address,
                "tx_hash":      rec.tx_hash,
                "verified":     "yes" if rec.verified else "no",
                "explorer_url": self.address_url(rec.name) or "",
            })
        return rows


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------

def _sepolia_registry_path() -> Path:
    return (
        Path(__file__).resolve().parent.parent
        / "contracts" / "deployments" / "sepolia.json"
    )


def _local_registry_path() -> Path:
    return (
        Path(__file__).resolve().parent.parent
        / "contracts" / "deployments" / "local.json"
    )


def load_registry(path: str | Path | None = None) -> OnchainRegistry | None:
    """Load and validate the JSON registry. Returns None if missing/empty."""
    p = Path(path) if path is not None else _sepolia_registry_path()
    if not p.is_file():
        return None
    try:
        raw = json.loads(p.read_text() or "{}")
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(raw, dict):
        return None

    # At least a chain_id or at least one contract must be present.
    chain_id = _coerce_int(raw.get("chain_id"))
    contracts_block = raw.get("contracts") or {}
    if not isinstance(contracts_block, dict):
        contracts_block = {}

    records: dict[str, ContractRecord] = {}
    for name, entry in contracts_block.items():
        if name not in CONTRACT_KEYS:
            # Ignore unknown keys silently — forward compat.
            continue
        if isinstance(entry, str):
            addr, tx, verified = entry, "", False
        elif isinstance(entry, dict):
            addr = str(entry.get("address") or "").strip()
            tx = str(entry.get("tx_hash") or entry.get("txHash") or "").strip()
            verified = bool(entry.get("verified", False))
        else:
            continue
        if not addr or not addr.startswith("0x") or len(addr) < 10:
            continue
        records[name] = ContractRecord(
            name=name,
            address=addr,
            tx_hash=tx,
            verified=verified,
        )

    if chain_id is None and not records:
        # Nothing useful to return.
        return None

    cid = chain_id if chain_id is not None else SEPOLIA_CHAIN_ID
    name = str(raw.get("chain_name") or chain_name(cid))
    base = str(raw.get("explorer_base") or explorer_base_for(cid) or "")
    return OnchainRegistry(
        chain_id=cid,
        chain_name=name,
        deployer=str(raw.get("deployer") or "").lower(),
        deployed_at=str(raw.get("deployed_at") or ""),
        explorer_base=base,
        rpc_hint=str(raw.get("rpc_hint") or ""),
        verified=bool(raw.get("verified", False)),
        contracts=records,
        source_path=str(p),
        raw=raw,
    )


def load_any_deployment() -> OnchainRegistry | None:
    """Prefer the rich JSON registry; fall back to the tiny key=value file.

    This is the single entry point the Reflex state layer should use.
    """
    reg = load_registry()
    if reg is not None and reg.is_present():
        return reg

    local = load_registry(_local_registry_path())
    if local is not None and local.is_present():
        return local

    legacy: Deployment | None = load_latest()
    if legacy is None:
        return reg  # may be a header-only registry with no contracts yet

    # Convert the legacy Deployment into the richer OnchainRegistry shape so
    # downstream UI code only has to handle one type.
    records = {
        name: ContractRecord(name=name, address=addr, tx_hash="", verified=False)
        for name, addr in legacy.addresses.items()
    }
    return OnchainRegistry(
        chain_id=LOCAL_ANVIL_CHAIN_ID,
        chain_name="Anvil (local)",
        deployer=legacy.owner,
        deployed_at="",
        explorer_base="",
        rpc_hint="http://127.0.0.1:8545",
        verified=False,
        contracts=records,
        source_path=legacy.source_path,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _coerce_int(val: Any) -> int | None:
    if val is None:
        return None
    try:
        if isinstance(val, str):
            val = val.strip()
            if val.lower().startswith("0x"):
                return int(val, 16)
        return int(val)
    except (TypeError, ValueError):
        return None


def short_address(address: str) -> str:
    if not address or len(address) < 10:
        return address or ""
    return f"{address[:6]}…{address[-4:]}"


__all__ = [
    "SEPOLIA_CHAIN_ID", "MAINNET_CHAIN_ID", "LOCAL_ANVIL_CHAIN_ID",
    "KNOWN_CHAINS", "EXPLORER_BASE",
    "chain_name", "is_sepolia", "explorer_base_for",
    "etherscan_address", "etherscan_tx", "short_address",
    "ContractRecord", "OnchainRegistry",
    "load_registry", "load_any_deployment",
]
