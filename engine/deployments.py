"""Read deployed contract addresses back into Python.

After `forge script script/Deploy.s.sol --broadcast` runs, the script
writes a key=value file at `contracts/deployments/latest.txt`. This
module parses that file so the Streamlit app and bridge can show which
addresses a call would target, closing the loop between on- and off-chain.

It is deliberately tiny and dependency-free — just enough to turn the
deploy output into a typed dict.

Usage:
    from engine.deployments import load_latest
    dep = load_latest()
    if dep:
        print(dep["CohortLedger"])  # "0x..."
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


CONTRACT_KEYS = (
    "CohortLedger",
    "FairnessGate",
    "MortalityOracle",
    "MortalityBasisOracle",
    "LongevaPool",
    "BenefitStreamer",
    "VestaRouter",
    "StressOracle",
    "BackstopVault",
)


@dataclass(frozen=True)
class Deployment:
    """All deployed addresses + the owner that deployed them."""
    owner: str
    addresses: Mapping[str, str]
    source_path: str

    def __getitem__(self, key: str) -> str:
        return self.addresses[key]

    def get(self, key: str, default: str | None = None) -> str | None:
        return self.addresses.get(key, default)

    def to_dict(self) -> dict[str, str]:
        d: dict[str, str] = {"owner": self.owner, **dict(self.addresses)}
        return d


def _default_path() -> Path:
    """Project-relative default — `contracts/deployments/latest.txt`."""
    return Path(__file__).resolve().parent.parent / "contracts" / "deployments" / "latest.txt"


def load_latest(path: str | Path | None = None) -> Deployment | None:
    """Load the most recent deployment, or `None` if none has been recorded.

    The file is plain text, one `key=value` per line. We only keep the
    contract keys listed in `CONTRACT_KEYS` plus the deployer `owner`.
    Addresses are normalised to lowercase 0x-hex; malformed lines are
    skipped silently so a partial file (e.g. deploy still in progress)
    doesn't crash the UI.
    """
    p = Path(path) if path is not None else _default_path()
    if not p.is_file():
        return None
    owner = ""
    addrs: dict[str, str] = {}
    for line in p.read_text().splitlines():
        if "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip()
        if not key or not val:
            continue
        if key == "owner":
            owner = val.lower()
        elif key in CONTRACT_KEYS:
            addrs[key] = val.lower()
    if not addrs and not owner:
        return None
    return Deployment(owner=owner, addresses=addrs, source_path=str(p))


__all__ = ["CONTRACT_KEYS", "Deployment", "load_latest"]
