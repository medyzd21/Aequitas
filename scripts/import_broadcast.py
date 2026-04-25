"""Populate `contracts/deployments/sepolia.json` from a Foundry broadcast log.

Reads the `run-latest.json` written by `forge script ... --broadcast` and
emits (or updates) the on-chain registry JSON that the Reflex app reads
through `engine.onchain_registry.load_registry`.

Usage
-----

    python3 scripts/import_broadcast.py \
        contracts/broadcast/Deploy.s.sol/11155111/run-latest.json \
        contracts/deployments/sepolia.json

Both paths are optional — they default to the canonical Sepolia
locations above. Pass ``--dry-run`` to print the resulting JSON to
stdout instead of writing the registry file. Pass ``--verified`` (flag
or comma-separated names) to mark contracts as Etherscan-verified.

Only contracts whose name matches the Aequitas contract set are kept —
unknown contracts are silently dropped so a forked deploy script can't
poison the registry.

Design notes
------------

* The broadcast file's addresses are lowercase, not checksummed. We
  store them verbatim — Etherscan happily resolves both forms, and
  keeping the case deterministic means this helper is idempotent.
* The script does **not** require pytest, web3, or eth-utils — pure
  stdlib only, so CI under the minimal pytest shim stays green.
* The emitted JSON preserves existing top-level keys (``$schema``,
  ``rpc_hint``, ``notes``) when updating an existing registry file so
  hand-authored hints survive.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import sys
from pathlib import Path
from typing import Any, Iterable

# Aequitas-only contract names. The script drops anything else so a
# careless Deploy.s.sol edit can't publish unrelated addresses.
ALLOWED_CONTRACTS = frozenset({
    "CohortLedger",
    "FairnessGate",
    "MortalityOracle",
    "MortalityBasisOracle",
    "InvestmentPolicyBallot",
    "ActuarialMethodRegistry",
    "ActuarialResultRegistry",
    "ActuarialVerifier",
    "LongevaPool",
    "BenefitStreamer",
    "VestaRouter",
    "StressOracle",
    "BackstopVault",
})

# Repo-relative defaults. Resolved at CLI-parse time.
REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BROADCAST = (
    REPO_ROOT / "contracts" / "broadcast" / "Deploy.s.sol" / "11155111"
    / "run-latest.json"
)
DEFAULT_REGISTRY = REPO_ROOT / "contracts" / "deployments" / "sepolia.json"

SEPOLIA_CHAIN_ID = 11155111
SEPOLIA_EXPLORER = "https://sepolia.etherscan.io"


# ---------------------------------------------------------------------------
# Core logic — pure functions, easy to test
# ---------------------------------------------------------------------------

def extract_create_transactions(broadcast: dict) -> list[dict]:
    """Return the list of CREATE transactions with a recognised contract."""
    txs = broadcast.get("transactions") or []
    out: list[dict] = []
    for tx in txs:
        if tx.get("transactionType") != "CREATE":
            continue
        name = tx.get("contractName") or ""
        addr = tx.get("contractAddress") or ""
        if not name or not addr:
            continue
        if name not in ALLOWED_CONTRACTS:
            continue
        out.append({
            "name":     name,
            "address":  addr,
            "tx_hash":  tx.get("hash") or "",
        })
    return out


def infer_deployer(broadcast: dict) -> str:
    """Pull the deployer EOA from the first CREATE tx, if any."""
    for tx in broadcast.get("transactions") or []:
        if tx.get("transactionType") != "CREATE":
            continue
        inner = tx.get("transaction") or {}
        frm = inner.get("from")
        if frm:
            return str(frm)
    return ""


def infer_deployed_at(broadcast: dict) -> str:
    """Return an ISO-8601 UTC timestamp if the broadcast log carries one.

    Foundry writes `timestamp` as seconds-since-epoch on older versions
    and milliseconds-since-epoch on 0.2.x+. We accept either and coerce.
    """
    ts = broadcast.get("timestamp")
    if ts is None:
        return ""
    try:
        ts_int = int(ts)
    except (TypeError, ValueError):
        return ""
    # Heuristic: anything > 10^12 is milliseconds.
    if ts_int > 10**12:
        ts_int //= 1000
    try:
        dt = _dt.datetime.fromtimestamp(ts_int, tz=_dt.timezone.utc)
    except (OverflowError, OSError, ValueError):
        return ""
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_verified_arg(
    verified_arg: bool | str | Iterable[str] | None,
    names: list[str],
) -> set[str]:
    """Normalise the --verified CLI flag into a set of contract names."""
    if verified_arg in (None, False):
        return set()
    if verified_arg is True:
        return set(names)
    if isinstance(verified_arg, str):
        tokens = [t.strip() for t in verified_arg.split(",") if t.strip()]
    else:
        tokens = [str(t).strip() for t in verified_arg if str(t).strip()]
    # If a user types `--verified all`, treat that as everyone.
    if any(t.lower() == "all" for t in tokens):
        return set(names)
    return {t for t in tokens if t in names}


def build_registry(
    broadcast: dict,
    existing: dict | None = None,
    chain_id: int = SEPOLIA_CHAIN_ID,
    verified: set[str] | None = None,
) -> dict:
    """Build a registry dict for `sepolia.json` from a broadcast log.

    `existing` lets callers preserve hand-authored metadata (rpc_hint,
    notes, $schema) across updates.
    """
    verified = verified or set()
    contracts_list = extract_create_transactions(broadcast)
    if not contracts_list:
        raise ValueError(
            "No CREATE transactions with a recognised contract name "
            "were found in the broadcast log — nothing to import."
        )

    deployer = infer_deployer(broadcast)
    deployed_at = infer_deployed_at(broadcast)

    contracts: dict[str, dict[str, Any]] = {}
    for row in contracts_list:
        name = row["name"]
        contracts[name] = {
            "address":  row["address"],
            "tx_hash":  row["tx_hash"],
            "verified": name in verified,
        }

    base: dict[str, Any] = {
        "chain_id":      int(chain_id),
        "chain_name":    "Sepolia Testnet",
        "deployer":      deployer,
        "deployed_at":   deployed_at,
        "explorer_base": SEPOLIA_EXPLORER,
        "verified":      bool(verified) and len(verified) == len(contracts),
        "contracts":     contracts,
    }

    if existing is None:
        return base

    # Preserve hand-authored metadata keys when updating.
    merged: dict[str, Any] = {}
    for k in ("$schema", "rpc_hint", "notes"):
        if k in existing:
            merged[k] = existing[k]
    merged.update(base)
    return merged


def write_registry(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, sort_keys=False)
        f.write("\n")


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# CLI glue
# ---------------------------------------------------------------------------

def _main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(
        description=(
            "Populate sepolia.json from a Foundry broadcast log."
        ),
    )
    p.add_argument(
        "broadcast",
        nargs="?",
        default=str(DEFAULT_BROADCAST),
        help="Path to run-latest.json (default: contracts/broadcast/"
             "Deploy.s.sol/11155111/run-latest.json)",
    )
    p.add_argument(
        "registry",
        nargs="?",
        default=str(DEFAULT_REGISTRY),
        help="Output registry JSON path "
             "(default: contracts/deployments/sepolia.json)",
    )
    p.add_argument(
        "--chain-id", type=int, default=SEPOLIA_CHAIN_ID,
        help="Chain id to stamp into the registry (default: 11155111).",
    )
    p.add_argument(
        "--verified", default="",
        help="Comma-separated contract names to mark as "
             "Etherscan-verified, or 'all' for every contract.",
    )
    p.add_argument(
        "--dry-run", action="store_true",
        help="Print the registry JSON to stdout instead of writing.",
    )
    args = p.parse_args(argv)

    broadcast_path = Path(args.broadcast).expanduser().resolve()
    registry_path  = Path(args.registry).expanduser().resolve()

    if not broadcast_path.exists():
        print(f"error: broadcast log not found: {broadcast_path}",
              file=sys.stderr)
        return 2

    broadcast = load_json(broadcast_path)
    existing = None
    if registry_path.exists():
        try:
            existing = load_json(registry_path)
        except json.JSONDecodeError:
            existing = None

    try:
        names = [r["name"] for r in extract_create_transactions(broadcast)]
        verified = _parse_verified_arg(args.verified or None, names)
        payload = build_registry(
            broadcast,
            existing=existing,
            chain_id=args.chain_id,
            verified=verified,
        )
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 3

    if args.dry_run:
        json.dump(payload, sys.stdout, indent=2, sort_keys=False)
        sys.stdout.write("\n")
        return 0

    write_registry(registry_path, payload)
    n = len(payload.get("contracts", {}))
    print(
        f"wrote {n} contracts to {registry_path} "
        f"(chain_id={payload['chain_id']}, deployer={payload['deployer'] or '—'})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
