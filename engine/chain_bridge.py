"""Python ↔ chain bridge.

Aequitas keeps actuarial math off-chain (pure Python) and executes it on
chain through a small set of contracts. This module is the *translation
layer* between those two worlds. Think of it as:

        Python engine output         chain_bridge            Solidity input
        --------------------         ------------            --------------
        ledger.cohort_valuation  ──► encode_baseline      ──► FairnessGate.setBaseline
        evaluate_proposal(...)   ──► encode_proposal      ──► FairnessGate.submitAndEvaluate
        simulate_fund(...)       ──► encode_stress_update ──► StressOracle.updateStressLevel
        Member(wallet, ...)      ──► encode_register      ──► CohortLedger.registerMember
        contribute(amount)       ──► encode_contribution  ──► CohortLedger.contribute

No web3 library is used — we just produce the plain call-data dicts the
user can feed into `cast send` or an ethers.js script. Keeping the bridge
dependency-free makes it trivially importable from Streamlit and from
tests, and makes the demo reproducible.

Key encodings used everywhere below:

  * PIU balances and EPVs          → int-/uint-256 scaled by 1e18.
  * Cohort buckets                 → uint16, floor(birthYear / 5) * 5.
  * Stress level                   → uint256 in [0, 1e18].
  * Reason codes / data hashes     → bytes32 (string → right-padded 32 bytes,
                                    hash → keccak-like 32-byte digest).
  * Addresses                      → "0x" + 40-hex chars, lower case.

These match the exact numeric conventions declared in the `contracts/src`
Solidity sources. If those ever change, update the `SCALE` constant and
the `cohort_of` helper below — every other encoder is derived from them.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, asdict
from typing import Any, Iterable, Mapping

from engine.models import Member, Proposal
from engine.ledger import CohortLedger


# ----------------------------------------------------------------- constants
SCALE = 10 ** 18                   # 1e18 fixed-point factor used across contracts
MAX_UINT16 = 2 ** 16 - 1
MAX_INT256 = 2 ** 255 - 1
MIN_INT256 = -(2 ** 255)
BYTES32_ZERO = "0x" + "0" * 64
ADDRESS_RE = re.compile(r"^0[xX][0-9a-fA-F]{40}$")
SHORT_ADDRESS_RE = re.compile(r"^0[xX][0-9a-fA-F]{1,40}$")


# ----------------------------------------------------------------- primitives

def to_fixed(x: float | int) -> int:
    """Convert a plain Python number into a 1e18 fixed-point integer.

    Uses round-half-to-even because it is the default Solidity-compatible
    rounding when you do `a * 1e18 / b` in JS before bignum — banker's
    rounding gets us reproducible behaviour across clients.
    """
    return int(round(float(x) * SCALE))


def from_fixed(x: int) -> float:
    """Inverse of `to_fixed` — useful when reading events back."""
    return float(x) / SCALE


def cohort_of(birth_year: int) -> int:
    """Same cohort rule used by both `engine.ledger` and `CohortLedger.sol`."""
    return (int(birth_year) // 5) * 5


def normalize_address(addr: str) -> str:
    """Validate and lowercase a 20-byte hex address.

    Accepts short demo IDs ("0xA001") for prototyping and left-pads them
    with zeros to the full 20 bytes, because the Streamlit demo uses
    human-readable identifiers. Production usage should always supply
    full-length addresses — in that case this is just a no-op validation.
    """
    if not isinstance(addr, str):
        raise ValueError(f"invalid EVM address (not a string): {addr!r}")
    if ADDRESS_RE.match(addr):
        return "0x" + addr[2:].lower()
    if SHORT_ADDRESS_RE.match(addr):
        hexpart = addr[2:].lower()
        return "0x" + hexpart.rjust(40, "0")
    raise ValueError(f"invalid EVM address: {addr!r}")


def string_to_bytes32(s: str) -> str:
    """Right-pad a short string (≤31 bytes ASCII) into a bytes32 hex string.

    Solidity's `bytes32("p95_gini")` does exactly this — left-aligns the
    bytes and zero-pads to 32. Anything longer than 31 bytes is rejected
    so we never silently truncate. The leading byte is free (bytes32
    permits 32 bytes of payload), but we reserve it for future-proofing.
    """
    if s is None:
        return BYTES32_ZERO
    raw = s.encode("utf-8")
    if len(raw) > 31:
        raise ValueError(f"string too long for bytes32: {s!r} ({len(raw)} bytes)")
    return "0x" + raw.hex() + "00" * (32 - len(raw))


def hash_bytes32(payload: bytes | str) -> str:
    """Make a deterministic bytes32 digest for an audit record.

    SHA-256 is used (not keccak-256) because it is available in stdlib and
    on-chain code only ever *stores* the hash — nothing on-chain recomputes
    it. The contract documents the provenance in its field name and event.
    """
    if isinstance(payload, str):
        payload = payload.encode("utf-8")
    return "0x" + hashlib.sha256(payload).hexdigest()


# ---------------------------------------------------------------- shape types

@dataclass
class ChainCall:
    """A dict-shaped intent to call `contract.function(args)` on chain.

    We don't submit it — the bridge only prepares it. A downstream script
    (or the Streamlit Contracts tab) can hand this to `cast send` or
    ethers.js. Keeping calls as plain data makes everything inspectable.
    """
    contract: str        # logical contract name ("CohortLedger", "FairnessGate", ...)
    function: str        # Solidity function name
    args: list[Any]      # positional args (already in chain-compatible shape)
    value_wei: int = 0   # native ETH to send alongside the call
    note: str = ""       # human-readable comment for the audit log

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


# ----------------------------------------------- CohortLedger — EquiGen write

def encode_register(member: Member) -> ChainCall:
    """Build a CohortLedger.registerMember(wallet, birthYear) call."""
    return ChainCall(
        contract="CohortLedger",
        function="registerMember",
        args=[normalize_address(member.wallet), int(member.birth_year)],
        note=f"register {member.wallet} (cohort {cohort_of(member.birth_year)})",
    )


def encode_contribution(wallet: str, amount: float, *, amount_unit: str = "wei") -> ChainCall:
    """Build a CohortLedger.contribute(wallet, amount) call.

    `amount` is interpreted as:
      * "wei"     → already in the chain's smallest unit (default);
      * "ether"   → multiplied by 1e18;
      * "scaled"  → multiplied by 1e18 with float rounding (same as ether).
    """
    if amount_unit == "wei":
        amt = int(amount)
    elif amount_unit in ("ether", "scaled"):
        amt = to_fixed(amount)
    else:
        raise ValueError(f"unknown amount_unit={amount_unit!r}")
    if amt <= 0:
        raise ValueError("amount must be positive")
    return ChainCall(
        contract="CohortLedger",
        function="contribute",
        args=[normalize_address(wallet), amt],
        note=f"contribute {amount}{amount_unit} for {wallet}",
    )


def encode_retire(wallet: str) -> ChainCall:
    return ChainCall(
        contract="CohortLedger",
        function="markRetired",
        args=[normalize_address(wallet)],
        note=f"retire {wallet}",
    )


# -------------------------------------------- FairnessGate — EquiGen write

def _cohort_epv_vectors(
    cohort_valuation: Mapping[int, Mapping[str, float]],
    multipliers: Mapping[int, float] | None = None,
) -> tuple[list[int], list[int], list[int]]:
    """Return (cohorts[uint16], epv_contribs[int256], epv_benefits[int256]).

    The benefit vector is multiplied by `multipliers` if given (this is how
    a Proposal is expressed on-chain). All EPV values are 1e18-scaled.
    """
    cohorts = sorted(int(c) for c in cohort_valuation.keys())
    contribs: list[int] = []
    benefits: list[int] = []
    for c in cohorts:
        if c < 0 or c > MAX_UINT16:
            raise ValueError(f"cohort {c} outside uint16 range")
        row = cohort_valuation[c]
        mult = float((multipliers or {}).get(c, 1.0))
        contribs.append(to_fixed(row["epv_contributions"]))
        benefits.append(to_fixed(row["epv_benefits"] * mult))
    return cohorts, contribs, benefits


def encode_baseline(cohort_valuation: Mapping[int, Mapping[str, float]]) -> ChainCall:
    """Build FairnessGate.setBaseline(cohorts, epvs).

    The on-chain baseline stores *benefit* EPVs (those are what future
    proposals perturb via cohort multipliers). Contribution EPVs are kept
    in the audit log for context.
    """
    cohorts, _contribs, benefits = _cohort_epv_vectors(cohort_valuation)
    return ChainCall(
        contract="FairnessGate",
        function="setBaseline",
        args=[cohorts, benefits],
        note=f"publish baseline for {len(cohorts)} cohorts",
    )


def encode_proposal(
    proposal: Proposal,
    cohort_valuation: Mapping[int, Mapping[str, float]],
    delta: float = 0.05,
) -> ChainCall:
    """Build FairnessGate.submitAndEvaluate(name, cohorts, newEpvs, delta).

    `delta` is the fractional corridor width — 0.05 → 5%. On-chain it's
    represented as a 1e18-scaled uint (so 5% → 5e16).
    """
    cohorts, _contribs, new_benefits = _cohort_epv_vectors(
        cohort_valuation, multipliers=proposal.multipliers
    )
    delta_fx = to_fixed(delta)
    if delta_fx < 0 or delta_fx > SCALE:
        raise ValueError("delta must be in [0, 1]")
    return ChainCall(
        contract="FairnessGate",
        function="submitAndEvaluate",
        args=[proposal.name, cohorts, new_benefits, delta_fx],
        note=f"evaluate proposal {proposal.name!r} with δ={delta:.4f}",
    )


# ---------------------------------------------- StressOracle — Astra write

def encode_stress_update(
    stress_level: float,
    reason: str,
    data_payload: bytes | str | None = None,
) -> ChainCall:
    """Build StressOracle.updateStressLevel(level, reason, dataHash).

    `stress_level` is a plain float in [0, 1] (e.g. 0.82 = "82% stressed")
    and we 1e18-scale it. `reason` is a short label ("p95_gini>threshold")
    and `data_payload` is the raw simulation output to hash into dataHash.
    """
    if not (0.0 <= float(stress_level) <= 1.0):
        raise ValueError("stress_level must be in [0, 1]")
    return ChainCall(
        contract="StressOracle",
        function="updateStressLevel",
        args=[
            to_fixed(stress_level),
            string_to_bytes32(reason),
            hash_bytes32(data_payload) if data_payload is not None else BYTES32_ZERO,
        ],
        note=f"stress={stress_level:.3f} because {reason!r}",
    )


# ---------------------------------------------- LongevaPool / Vesta writes

def encode_pool_deposit(wallet: str, amount_ether: float) -> ChainCall:
    return ChainCall(
        contract="LongevaPool",
        function="deposit",
        args=[normalize_address(wallet), to_fixed(amount_ether)],
        value_wei=to_fixed(amount_ether),
        note=f"mint pool shares for {wallet} ({amount_ether} ETH)",
    )


def encode_open_retirement(
    wallet: str,
    lump_ether: float,
    annual_benefit_ether: float,
    start_timestamp: int = 0,
) -> ChainCall:
    """Build VestaRouter.openRetirement(wallet, amount, annualBenefit, startTs)."""
    return ChainCall(
        contract="VestaRouter",
        function="openRetirement",
        args=[
            normalize_address(wallet),
            to_fixed(lump_ether),
            to_fixed(annual_benefit_ether),
            int(start_timestamp),
        ],
        note=f"start retirement stream for {wallet}: {annual_benefit_ether} ETH/yr",
    )


# -------------------------------------------- BackstopVault — Astra writes

def encode_backstop_deposit(amount_ether: float) -> ChainCall:
    """Build BackstopVault.deposit() with native ETH attached.

    Used to seed the reserve before any stress event. The Python side
    typically computes the target reserve size from the Monte-Carlo p95
    shortfall; governance then deposits that many ETH here.
    """
    if amount_ether <= 0:
        raise ValueError("deposit amount must be positive")
    return ChainCall(
        contract="BackstopVault",
        function="deposit",
        args=[],
        value_wei=to_fixed(amount_ether),
        note=f"seed backstop reserve with {amount_ether} ETH",
    )


def encode_backstop_release(amount_ether: float) -> ChainCall:
    """Build BackstopVault.release(amount).

    The contract will revert unless `stressOracle.stressLevel() ≥
    releaseThreshold` AND `amount ≤ reserve * perCallCapBps / 10_000`.
    The Python side decides the amount from its simulation output.
    """
    if amount_ether <= 0:
        raise ValueError("release amount must be positive")
    return ChainCall(
        contract="BackstopVault",
        function="release",
        args=[to_fixed(amount_ether)],
        note=f"release {amount_ether} ETH from backstop to beneficiary",
    )


# ------------------------------------------------------- bulk helpers

def ledger_to_chain_calls(ledger: CohortLedger) -> list[ChainCall]:
    """Replay an in-Python ledger as a sequence of chain calls.

    For every existing member we emit a registerMember + a contribute call
    (skipping contribute if total_contributions is zero). This is what the
    Streamlit app uses to produce "what the contract would have seen".
    """
    calls: list[ChainCall] = []
    for m in ledger.get_all_members():
        calls.append(encode_register(m))
        if m.total_contributions > 0:
            calls.append(encode_contribution(
                m.wallet, m.total_contributions, amount_unit="ether"
            ))
        if not m.active:  # placeholder for retired flag — MVP treats !active as retired
            calls.append(encode_retire(m.wallet))
    return calls


def proposal_to_chain_calls(
    ledger: CohortLedger,
    proposal: Proposal,
    delta: float = 0.05,
) -> list[ChainCall]:
    """Full proposal hand-off: baseline publish + proposal submit."""
    cv = ledger.cohort_valuation()
    return [encode_baseline(cv), encode_proposal(proposal, cv, delta=delta)]


def stress_from_simulation(
    stress_level: float,
    reason: str,
    simulation_summary: Mapping[str, Any],
) -> ChainCall:
    """Convert a Monte-Carlo summary into a StressOracle update.

    `simulation_summary` is serialized and hashed so auditors can verify
    off-chain what data triggered the on-chain state change.
    """
    import json
    blob = json.dumps(simulation_summary, sort_keys=True, default=str).encode("utf-8")
    return encode_stress_update(stress_level, reason, blob)


# ------------------------------------------------------ pretty serialisation

def calls_to_json(calls: Iterable[ChainCall]) -> list[dict[str, Any]]:
    """JSON-friendly list of calls. Used by the Streamlit Contracts tab and
    by anyone who wants to pipe this into a forge script."""
    return [c.as_dict() for c in calls]


__all__ = [
    "SCALE",
    "to_fixed",
    "from_fixed",
    "cohort_of",
    "normalize_address",
    "string_to_bytes32",
    "hash_bytes32",
    "ChainCall",
    "encode_register",
    "encode_contribution",
    "encode_retire",
    "encode_baseline",
    "encode_proposal",
    "encode_stress_update",
    "encode_pool_deposit",
    "encode_open_retirement",
    "encode_backstop_deposit",
    "encode_backstop_release",
    "ledger_to_chain_calls",
    "proposal_to_chain_calls",
    "stress_from_simulation",
    "calls_to_json",
]
