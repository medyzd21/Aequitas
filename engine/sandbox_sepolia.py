"""Sandbox Sepolia proof flow.

Plans and (optionally) executes the small deterministic on-chain demo from
the Sandbox roster. Plain Python, no web3/eth_account requirement at import
time — the runner shells out to ``cast send`` per step. Tests use the
default ``dry_run=True`` path so they never need a live RPC.

Step ordering, per the user-facing requirements:

    Member lifecycle
        1. register_members        (operator)   CohortLedger.registerMember
        2. publish_piu_price       (operator)   CohortLedger.setPiuPrice
        3. post_contributions      (operator)   CohortLedger.contribute
        4. open_retirement         (operator)   VestaRouter.openRetirement
                                                (preceded by markRetired)

    Fairness governance
        5. fairness_baseline       (operator)   FairnessGate.setBaseline
        6. fairness_proposal_pass  (operator)   FairnessGate.submitAndEvaluate
        7. fairness_proposal_fail  (operator)   FairnessGate.submitAndEvaluate

    Investment governance
        8.  ballot_create          (operator)   InvestmentPolicyBallot.createBallot
        9.  ballot_weights         (reporter)   InvestmentPolicyBallot.setBallotWeights
        10. ballot_votes           (member)     InvestmentPolicyBallot.castVote
        11. ballot_finalize        (operator)   InvestmentPolicyBallot.finalizeBallot

    Actuarial proof (optional, only if registry contracts are deployed)
        12. actuarial_publish      (operator)   ActuarialResultRegistry.publishResultBundle

Only step 10 (``castVote``) requires a *member* signature; every other step
is signed by the operator/deployer key. The runner therefore looks up the
member private key from ``sandbox_wallets.json`` for that step alone.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Mapping, Sequence

from engine.onchain_registry import (
    OnchainRegistry,
    SEPOLIA_CHAIN_ID,
    etherscan_address,
    etherscan_tx,
)
from engine.sandbox_wallets import (
    SandboxWalletRecord,
    mask_secrets_in_text,
)


# ---------------------------------------------------------------- constants

# Contracts the proof flow will touch.
REQUIRED_CONTRACTS: tuple[str, ...] = (
    "CohortLedger",
    "LongevaPool",
    "VestaRouter",
    "BenefitStreamer",
    "FairnessGate",
    "InvestmentPolicyBallot",
)

# Optional — only used if the actuarial proof step is wired.
OPTIONAL_CONTRACTS: tuple[str, ...] = (
    "ActuarialMethodRegistry",
    "ActuarialResultRegistry",
)


# Step keys, in canonical execution order.
STEP_ORDER: tuple[str, ...] = (
    "register_members",
    "publish_piu_price",
    "post_contributions",
    "fund_protocol_pool",   # seeds LongevaPool before openRetirement
    "open_retirement",
    "fairness_baseline",
    "fairness_proposal_pass",
    "fairness_proposal_fail",
    "ballot_create",
    "ballot_weights",
    "ballot_votes",
    "ballot_finalize",
    "actuarial_publish",
)


# Maps each step to the actor / signing role.
#   "operator" = deployer/operator EOA (DEPLOYER_PK)
#   "member"   = sandbox member EOA (per-member private key)
STEP_SIGNERS: dict[str, str] = {
    "register_members":       "operator",
    "publish_piu_price":      "operator",
    "post_contributions":     "operator",
    "fund_protocol_pool":     "operator",
    "open_retirement":        "operator",
    "fairness_baseline":      "operator",
    "fairness_proposal_pass": "operator",
    "fairness_proposal_fail": "operator",
    "ballot_create":          "operator",
    "ballot_weights":         "operator",
    "ballot_votes":           "member",
    "ballot_finalize":        "operator",
    "actuarial_publish":      "operator",
}

# Maps each step to (contract, function).
STEP_TARGETS: dict[str, tuple[str, str]] = {
    "register_members":       ("CohortLedger",            "registerMember"),
    "publish_piu_price":      ("CohortLedger",            "setPiuPrice"),
    "post_contributions":     ("CohortLedger",            "contribute"),
    "fund_protocol_pool":     ("LongevaPool",             "simulateYield"),
    "open_retirement":        ("VestaRouter",             "openRetirement"),
    "fairness_baseline":      ("FairnessGate",            "setBaseline"),
    "fairness_proposal_pass": ("FairnessGate",            "submitAndEvaluate"),
    "fairness_proposal_fail": ("FairnessGate",            "submitAndEvaluate"),
    "ballot_create":          ("InvestmentPolicyBallot",  "createBallot"),
    "ballot_weights":         ("InvestmentPolicyBallot",  "setBallotWeights"),
    "ballot_votes":           ("InvestmentPolicyBallot",  "castVote"),
    "ballot_finalize":        ("InvestmentPolicyBallot",  "finalizeBallot"),
    "actuarial_publish":      ("ActuarialResultRegistry", "publishResultBundle"),
}

STEP_LABELS: dict[str, str] = {
    "register_members":       "Register sandbox members",
    "publish_piu_price":      "Publish sandbox PIU price",
    "post_contributions":     "Post sandbox contributions (mint PIUs)",
    "fund_protocol_pool":     "Fund protocol retirement pool (seed LongevaPool)",
    "open_retirement":        "Open one retirement",
    "fairness_baseline":      "Publish fairness baseline",
    "fairness_proposal_pass": "Submit fairness proposal that passes",
    "fairness_proposal_fail": "Submit fairness proposal that fails",
    "ballot_create":          "Create investment ballot",
    "ballot_weights":         "Publish ballot voting weights",
    "ballot_votes":           "Cast sandbox investment votes",
    "ballot_finalize":        "Finalize investment policy",
    "actuarial_publish":      "Publish actuarial method/result bundle",
}


# ---------------------------------------------------------------- env / sanity

@dataclass(frozen=True)
class EnvCheck:
    ok: bool
    rpc_url: str
    deployer_pk_present: bool
    cast_path: str
    devtools_enabled: bool
    error: str = ""


def check_env(env: Mapping[str, str] | None = None) -> EnvCheck:
    e = dict(env if env is not None else os.environ)
    rpc = (e.get("SEPOLIA_RPC_URL") or "").strip()
    pk = (e.get("DEPLOYER_PK") or "").strip()
    devtools = str(e.get("AEQUITAS_DEVTOOLS", "")).strip().lower() in {"1", "true", "yes", "on"}
    cast_path = shutil.which("cast") or ""

    errors = []
    if not rpc:
        errors.append("SEPOLIA_RPC_URL is not set")
    if not pk:
        errors.append("DEPLOYER_PK is not set")
    if not cast_path:
        errors.append("foundry's `cast` is not on PATH")
    if not devtools:
        errors.append("AEQUITAS_DEVTOOLS is not enabled")
    return EnvCheck(
        ok=not errors,
        rpc_url=rpc,
        deployer_pk_present=bool(pk),
        cast_path=cast_path,
        devtools_enabled=devtools,
        error="; ".join(errors),
    )


@dataclass(frozen=True)
class RegistryCheck:
    ok: bool
    missing_required: tuple[str, ...]
    missing_optional: tuple[str, ...]
    on_sepolia: bool


def check_registry(registry: OnchainRegistry | None) -> RegistryCheck:
    if registry is None:
        return RegistryCheck(
            ok=False,
            missing_required=tuple(REQUIRED_CONTRACTS),
            missing_optional=tuple(OPTIONAL_CONTRACTS),
            on_sepolia=False,
        )
    missing_req = tuple(c for c in REQUIRED_CONTRACTS if not registry.address_of(c))
    missing_opt = tuple(c for c in OPTIONAL_CONTRACTS if not registry.address_of(c))
    return RegistryCheck(
        ok=not missing_req,
        missing_required=missing_req,
        missing_optional=missing_opt,
        on_sepolia=int(registry.chain_id) == SEPOLIA_CHAIN_ID,
    )


# ---------------------------------------------------------------- step state

@dataclass
class StepResult:
    key: str
    label: str
    contract: str
    function: str
    actor: str               # "operator" | "member"
    member_wallet: str = ""  # set only for member-signed or per-member operator calls
    # status values:
    #   "not_run"   — not executed yet
    #   "simulated" — completed in dry-run mode (no on-chain tx)
    #   "pending"   — live: cast send returned, awaiting receipt
    #   "confirmed" — live: receipt fetched, transaction succeeded
    #   "failed"    — live: cast send or receipt reported failure
    #   "skipped"   — nothing to do (e.g. optional contract not deployed)
    status: str = "not_run"
    mode: str = "dry_run"    # "dry_run" | "live"
    tx_hash: str = ""
    explorer_url: str = ""
    gas_used: int = 0
    error: str = ""
    note: str = ""
    run_id: str = ""

    def to_row(self) -> dict[str, Any]:
        d = asdict(self)
        d["short_hash"] = (self.tx_hash[:10] + "…") if self.tx_hash else ""
        return d


def empty_steps() -> list[StepResult]:
    out: list[StepResult] = []
    for key in STEP_ORDER:
        contract, function = STEP_TARGETS[key]
        out.append(StepResult(
            key=key,
            label=STEP_LABELS[key],
            contract=contract,
            function=function,
            actor=STEP_SIGNERS[key],
        ))
    return out


# ---------------------------------------------------------------- runner

@dataclass
class RunContext:
    env: Mapping[str, str]
    registry: OnchainRegistry
    wallets: Sequence[SandboxWalletRecord]
    dry_run: bool = True
    sleep_between: float = 0.0    # for live runs, throttle a bit
    receipt_timeout_s: int = 120  # how long to wait for a Sepolia receipt
    run_id: str = ""
    ballot_id: int = 0            # set after ballot_create succeeds
    ballot_opens_at: int = 0      # set at ballot_create plan time
    ballot_closes_at: int = 0     # set at ballot_create plan time

    @property
    def mode_label(self) -> str:
        return "dry_run" if self.dry_run else "live"


@dataclass
class CastInvocation:
    """A planned ``cast send`` invocation. Useful for dry-run + tests."""
    contract: str
    contract_address: str
    function: str
    args: list[str]
    actor: str
    signer_address: str
    member_wallet: str = ""
    value_wei: int = 0          # if > 0, passed as --value (payable functions)

    def cmd_preview(self, *, mask_pk: bool = True) -> list[str]:
        """Shell-safe command preview that never embeds the raw private key."""
        cmd = ["cast", "send", self.contract_address, self.function, *self.args]
        if self.value_wei > 0:
            cmd += ["--value", str(self.value_wei)]
        cmd += ["--private-key", "[REDACTED]" if mask_pk else "<pk>",
                "--rpc-url", "$SEPOLIA_RPC_URL"]
        return cmd


def _operator_signer(wallets: Sequence[SandboxWalletRecord], env: Mapping[str, str]) -> str:
    """Return the operator/deployer address for display.

    We never embed the private key into UI rows; the address is purely
    informational. If ``DEPLOY_OPERATOR`` is set we surface that.
    """
    return str(env.get("DEPLOY_OPERATOR") or env.get("DEPLOYER_ADDRESS") or "operator").lower() or "operator"


def _select_retiree(wallets: Sequence[SandboxWalletRecord]) -> SandboxWalletRecord | None:
    for w in wallets:
        if w.role == "near_retiree":
            return w
    return wallets[0] if wallets else None


def _plan_step(step: StepResult, ctx: RunContext) -> list[CastInvocation]:
    """Return the cast invocations for ``step``.

    A single logical step can fan out into multiple cast calls (e.g.
    register N members, post N contributions, cast N votes).
    """
    contract = step.contract
    address = ctx.registry.address_of(contract) or ""
    op = _operator_signer(ctx.wallets, ctx.env)

    if step.key == "register_members":
        return [
            CastInvocation(
                contract=contract, contract_address=address, function="registerMember",
                args=[w.address, str(w.cohort)],
                actor="operator", signer_address=op, member_wallet=w.address,
            )
            for w in ctx.wallets
        ]

    if step.key == "publish_piu_price":
        # 1.05 * 1e18 — a small, deterministic bump.
        price_fx = str(int(1.05 * 10**18))
        return [CastInvocation(
            contract=contract, contract_address=address, function="setPiuPrice",
            args=[price_fx], actor="operator", signer_address=op,
        )]

    if step.key == "post_contributions":
        # contribute amounts in wei (1 ETH per active member, scaled).
        invs: list[CastInvocation] = []
        for w in ctx.wallets:
            if w.role == "near_retiree":
                amount = "5000000000000000000"   # 5 ETH-equivalent
            elif w.role == "active":
                amount = "3000000000000000000"
            else:
                amount = "1000000000000000000"
            invs.append(CastInvocation(
                contract=contract, contract_address=address, function="contribute",
                args=[w.address, amount],
                actor="operator", signer_address=op, member_wallet=w.address,
            ))
        return invs

    if step.key == "fund_protocol_pool":
        # Seed LongevaPool so openRetirement can pull initialFunding.
        # simulateYield() is payable and requires YIELD_ROLE (granted to owner/deployer).
        # We send 0.002 ETH so there's enough headroom for the retirement step.
        pool_amount = 2_000_000_000_000_000   # 0.002 ETH
        return [CastInvocation(
            contract=contract, contract_address=address, function="simulateYield()",
            args=[], actor="operator", signer_address=op,
            value_wei=pool_amount,
        )]

    if step.key == "open_retirement":
        retiree = _select_retiree(ctx.wallets)
        if retiree is None:
            return []
        ledger_addr = ctx.registry.address_of("CohortLedger") or ""
        # Step a) markRetired on the ledger; step b) openRetirement on VestaRouter.
        # initialFunding is small (0.001 ETH) — pool must be seeded by fund_protocol_pool first.
        initial_funding = "1000000000000000"    # 0.001 ETH
        annual_benefit  = "100000000000000"     # 0.0001 ETH/yr (demo amount)
        invs = [
            CastInvocation(
                contract="CohortLedger", contract_address=ledger_addr, function="markRetired",
                args=[retiree.address], actor="operator", signer_address=op,
                member_wallet=retiree.address,
            ),
            CastInvocation(
                contract=contract, contract_address=address, function="openRetirement",
                args=[
                    retiree.address,
                    initial_funding,
                    annual_benefit,
                    "0",   # startTs = block.timestamp
                ],
                actor="operator", signer_address=op, member_wallet=retiree.address,
            ),
        ]
        return invs

    if step.key == "fairness_baseline":
        cohorts = sorted({int(w.cohort) for w in ctx.wallets})
        # Match Solidity tuple shape; cast accepts "[v1,v2,…]".
        cohorts_arg = "[" + ",".join(str(c) for c in cohorts) + "]"
        epvs_arg = "[" + ",".join(str(int(1e21)) for _ in cohorts) + "]"
        return [CastInvocation(
            contract=contract, contract_address=address, function="setBaseline",
            args=[cohorts_arg, epvs_arg], actor="operator", signer_address=op,
        )]

    if step.key in ("fairness_proposal_pass", "fairness_proposal_fail"):
        cohorts = sorted({int(w.cohort) for w in ctx.wallets})
        cohorts_arg = "[" + ",".join(str(c) for c in cohorts) + "]"
        if step.key == "fairness_proposal_pass":
            # Tiny, well-within-corridor perturbation (0.5%).
            new_epvs = [int(1e21 * 1.005) for _ in cohorts]
            delta = str(int(0.05 * 10**18))    # 5% corridor
            name = "Sandbox PASS proposal"
        else:
            # First cohort gets a much larger bump than others — busts the corridor.
            new_epvs = [int(1e21 * 1.30)] + [int(1e21) for _ in cohorts[1:]]
            delta = str(int(0.05 * 10**18))    # same corridor; payload makes it fail
            name = "Sandbox FAIL proposal"
        epvs_arg = "[" + ",".join(str(v) for v in new_epvs) + "]"
        return [CastInvocation(
            contract=contract, contract_address=address, function="submitAndEvaluate",
            args=[name, cohorts_arg, epvs_arg, delta],
            actor="operator", signer_address=op,
        )]

    if step.key == "ballot_create":
        # opensAt must be in the FUTURE so setBallotWeights can run first.
        # closesAt must be after opensAt (short voting window for demo).
        # dry-run uses stable dummy timestamps.
        if not ctx.dry_run:
            now_ts = int(time.time())
            opens = now_ts + 60    # 60s to publish weights before voting opens
            closes = now_ts + 120  # 60s voting window
        else:
            opens  = 1700000060    # stable dry-run value
            closes = 1700000120
        # Store timing on context so ballot_votes / ballot_finalize can wait.
        ctx.ballot_opens_at  = opens
        ctx.ballot_closes_at = closes
        portfolio_ids = "[0x" + "61".ljust(64, "0") + ",0x" + "62".ljust(64, "0") + "]"
        allocation_hashes = "[0x" + "11" * 32 + ",0x" + "22" * 32 + "]"
        return [CastInvocation(
            contract=contract, contract_address=address, function="createBallot",
            args=["Sandbox investment policy ballot", portfolio_ids, allocation_hashes,
                  str(opens), str(closes)],
            actor="operator", signer_address=op,
        )]

    if step.key == "ballot_weights":
        ballot_id = str(ctx.ballot_id)
        voters = "[" + ",".join(w.address for w in ctx.wallets) + "]"
        weights = "[" + ",".join("100" for _ in ctx.wallets) + "]"
        return [CastInvocation(
            contract=contract, contract_address=address, function="setBallotWeights",
            args=[ballot_id, voters, weights],
            actor="operator", signer_address=op,
        )]

    if step.key == "ballot_votes":
        # *** member-signed step ***
        # Each member's address must have received a weight via setBallotWeights.
        ballot_id = str(ctx.ballot_id)
        port_a = "0x" + "61".ljust(64, "0")
        port_b = "0x" + "62".ljust(64, "0")
        invs: list[CastInvocation] = []
        for i, w in enumerate(ctx.wallets):
            target = port_a if i < (len(ctx.wallets) // 2 + 1) else port_b
            invs.append(CastInvocation(
                contract=contract, contract_address=address, function="castVote",
                args=[ballot_id, target],
                actor="member", signer_address=w.address, member_wallet=w.address,
            ))
        return invs

    if step.key == "ballot_finalize":
        return [CastInvocation(
            contract=contract, contract_address=address, function="finalizeBallot",
            args=[str(ctx.ballot_id)], actor="operator", signer_address=op,
        )]

    if step.key == "actuarial_publish":
        if not address:
            return []
        # Use deterministic non-zero keys derived from run_id so repeated
        # runs create distinct bundles (AlreadyPublished is idempotent).
        import hashlib as _hl
        seed = ctx.run_id or "sandbox_demo"
        def _h(tag: str) -> str:
            return "0x" + _hl.sha256(f"{seed}:{tag}".encode()).hexdigest()
        return [CastInvocation(
            contract=contract, contract_address=address, function="publishResultBundle",
            args=[
                _h("result_bundle"),
                _h("parameter_set"),
                _h("valuation_snapshot"),
                _h("mortality_method"),
                _h("epv_method"),
                _h("mwr_method"),
                _h("fairness_method"),
                _h("scheme_summary"),
                _h("cohort_digest"),
                _h("result_hash"),
            ],
            actor="operator", signer_address=op,
        )]

    return []


@dataclass(frozen=True)
class InvocationResult:
    ok: bool
    tx_hash: str = ""
    error: str = ""
    gas_used: int = 0
    receipt_status: str = ""    # "0x1" success, "0x0" reverted, "" unknown


def _signing_key_for(inv: CastInvocation, ctx: RunContext) -> tuple[str, str]:
    """Resolve (private_key, error). Empty pk + non-empty error means failure."""
    if inv.actor == "member":
        member = next(
            (w for w in ctx.wallets if w.address.lower() == inv.member_wallet.lower()),
            None,
        )
        if member is None:
            return "", f"no sandbox key for member {inv.member_wallet}"
        return member.private_key, ""
    pk = (ctx.env.get("DEPLOYER_PK") or "").strip()
    if not pk:
        return "", "DEPLOYER_PK is not set"
    return pk, ""


def _execute_invocation(inv: CastInvocation, ctx: RunContext) -> InvocationResult:
    """Run a single ``cast send`` against Sepolia (or simulate it in dry-run).

    In dry-run mode we never call ``subprocess`` and never produce a real
    Etherscan URL; the caller marks the step as "simulated".
    """
    if ctx.dry_run:
        # Stable, recognisable fake tx hash that still passes 0x-32-byte shape.
        return InvocationResult(ok=True, tx_hash="0x" + ("dd" * 32), receipt_status="0x1")

    cast = shutil.which("cast")
    if not cast:
        return InvocationResult(ok=False, error="cast not on PATH")

    pk, pk_err = _signing_key_for(inv, ctx)
    if not pk:
        return InvocationResult(ok=False, error=pk_err)

    rpc = (ctx.env.get("SEPOLIA_RPC_URL") or "").strip()
    if not rpc:
        return InvocationResult(ok=False, error="SEPOLIA_RPC_URL is not set")

    cmd = [cast, "send", inv.contract_address, inv.function, *inv.args]
    if inv.value_wei > 0:
        cmd += ["--value", str(inv.value_wei)]
    cmd += ["--private-key", pk, "--rpc-url", rpc, "--json"]
    try:
        out = subprocess.run(
            cmd, check=False, capture_output=True, text=True,
            timeout=max(60, ctx.receipt_timeout_s),
        )
    except (subprocess.SubprocessError, OSError) as exc:
        return InvocationResult(ok=False, error=mask_secrets_in_text(str(exc), [pk]))
    if out.returncode != 0:
        err = mask_secrets_in_text((out.stderr or out.stdout or "").strip(), [pk])
        return InvocationResult(ok=False, error=err)
    try:
        receipt = json.loads(out.stdout or "{}")
    except json.JSONDecodeError:
        return InvocationResult(
            ok=False, error=mask_secrets_in_text("malformed cast output", [pk]),
        )
    tx = str(receipt.get("transactionHash") or "").strip()
    if not tx:
        return InvocationResult(ok=False, error="no transactionHash in cast receipt")
    status = str(receipt.get("status") or "").strip()
    gas = _parse_int(receipt.get("gasUsed") or receipt.get("cumulativeGasUsed") or 0)
    if status and status != "0x1":
        return InvocationResult(
            ok=False, tx_hash=tx, gas_used=gas, receipt_status=status,
            error=f"transaction reverted (status={status})",
        )
    return InvocationResult(ok=True, tx_hash=tx, gas_used=gas, receipt_status=status or "0x1")


def _parse_int(val: Any) -> int:
    if val is None or val == "":
        return 0
    try:
        if isinstance(val, str):
            return int(val, 16) if val.lower().startswith("0x") else int(val)
        return int(val)
    except (TypeError, ValueError):
        return 0


def _cast_call(address: str, sig: str, args: list[str], env: Mapping[str, str]) -> str:
    """Run ``cast call`` (read-only) and return stdout.strip(). Empty on failure."""
    cast = shutil.which("cast")
    rpc = (env.get("SEPOLIA_RPC_URL") or "").strip()
    if not cast or not rpc or not address:
        return ""
    try:
        out = subprocess.run(
            [cast, "call", address, sig, *args, "--rpc-url", rpc],
            check=False, capture_output=True, text=True, timeout=30,
        )
    except (subprocess.SubprocessError, OSError):
        return ""
    if out.returncode != 0:
        return ""
    return (out.stdout or "").strip()


# ---- idempotent-revert handling ----------------------------------------

# Known revert signatures that indicate a state already exists on-chain.
# Only these are silently skipped; all other errors are treated as fatal.
_IDEMPOTENT_REVERTS: frozenset[str] = frozenset({
    "alreadyregistered",          # CohortLedger.registerMember
    "already registered",
    "alreadyvoted",               # InvestmentPolicyBallot.castVote
    "already voted",
    "ballotalreadyfinalized",     # InvestmentPolicyBallot.finalizeBallot
    "ballot already finalized",
    "alreadypublished",           # ActuarialResultRegistry.*
    "already published",
    "duplicateweightsnapshot",    # InvestmentPolicyBallot.setBallotWeights (re-run)
    "duplicate weight snapshot",
    "inactivemember",             # CohortLedger.contribute — member already retired
    "inactive member",
    "streamalreadyexists",        # BenefitStreamer.startStream — repeated openRetirement
    "stream already exists",
})

# Raw 4-byte ABI selectors for known idempotent custom errors.
# Live RPC nodes often return only the hex-encoded revert data (e.g.
# "data: \"0xf7476063000...\"") without a decoded error name.  These selectors
# are the first 4 bytes of keccak256(error_signature).
_IDEMPOTENT_SELECTORS: frozenset[str] = frozenset({
    "0xf7476063",   # InactiveMember(address)      — CohortLedger.contribute
    "0xc6fd1730",   # StreamAlreadyExists(address)  — BenefitStreamer.startStream
})


def _is_idempotent_revert(error: str) -> bool:
    """Return True iff ``error`` is a known already-on-chain condition.

    Checks both decoded error-name strings and raw 4-byte ABI selectors so
    that live-RPC errors carrying only hex revert data are also caught.
    """
    low = (error or "").lower()
    return any(pat in low for pat in _IDEMPOTENT_REVERTS) or any(
        sel in low for sel in _IDEMPOTENT_SELECTORS
    )


def _plain_error(error: str) -> str:
    """Convert a known technical revert into a readable message."""
    low = (error or "").lower()
    if "alreadyregistered" in low or "already registered" in low:
        return "member already registered on-chain (skipped)"
    if "insufficientassets" in low or "insufficient assets" in low:
        return (
            "protocol pool has insufficient assets — "
            "run 'Fund protocol retirement pool' before 'Open one retirement'"
        )
    if "ballotnotopen" in low or "ballot not open" in low:
        return (
            "ballot not open — weights must be published before opensAt; "
            "votes must be cast between opensAt and closesAt"
        )
    if "ballotnotclosed" in low or "ballot not closed" in low:
        return "ballot still open — finalizeBallot requires block.timestamp ≥ closesAt"
    if "ineligiblevoter" in low or "ineligible voter" in low:
        return (
            "ineligible voter — no weight recorded for this address; "
            "run 'Publish ballot voting weights' before casting votes"
        )
    if "invalidparams" in low or "invalid params" in low:
        return "invalid params — ensure all bytes32 keys are non-zero"
    if "inactivemember" in low or "inactive member" in low or "0xf7476063" in low:
        return "member already retired/inactive — contribution skipped (skipped_existing)"
    if "streamalreadyexists" in low or "stream already exists" in low or "0xc6fd1730" in low:
        return "retirement stream already exists — openRetirement skipped (skipped_existing)"
    return error


# ---------------------------------------------------------------- balance + funding

def get_balance_wei(address: str, env: Mapping[str, str]) -> int | None:
    """Return Sepolia balance in wei via ``cast balance``. ``None`` on failure."""
    cast = shutil.which("cast")
    rpc = (env.get("SEPOLIA_RPC_URL") or "").strip()
    if not cast or not rpc:
        return None
    try:
        out = subprocess.run(
            [cast, "balance", address, "--rpc-url", rpc],
            check=False, capture_output=True, text=True, timeout=30,
        )
    except (subprocess.SubprocessError, OSError):
        return None
    if out.returncode != 0:
        return None
    return _parse_int((out.stdout or "").strip())


@dataclass
class FundingResult:
    address: str
    label: str
    balance_before_wei: int = 0
    balance_after_wei: int = 0
    funded_wei: int = 0
    tx_hash: str = ""
    explorer_url: str = ""
    status: str = "not_run"   # "not_run" | "skipped" | "funded" | "failed"
    error: str = ""

    def to_row(self) -> dict[str, Any]:
        d = asdict(self)
        d["balance_before_eth"] = self.balance_before_wei / 1e18
        d["balance_after_eth"] = self.balance_after_wei / 1e18
        d["funded_eth"] = self.funded_wei / 1e18
        return d


def fund_sandbox_wallets(
    wallets: Sequence[SandboxWalletRecord],
    env: Mapping[str, str],
    *,
    threshold_wei: int,
    amount_wei: int,
    dry_run: bool = True,
) -> list[FundingResult]:
    """Top up each member wallet from DEPLOYER_PK if below ``threshold_wei``.

    Idempotent — wallets already at or above threshold are reported as
    ``skipped``. In dry-run mode we still report current balances but never
    invoke ``cast send``.
    """
    pk = (env.get("DEPLOYER_PK") or "").strip()
    rpc = (env.get("SEPOLIA_RPC_URL") or "").strip()
    cast = shutil.which("cast")

    results: list[FundingResult] = []
    for w in wallets:
        fr = FundingResult(address=w.address, label=w.label)
        bal = get_balance_wei(w.address, env)
        if bal is None and not dry_run:
            fr.status = "failed"
            fr.error = "could not query balance (cast/rpc unavailable)"
            results.append(fr)
            continue
        fr.balance_before_wei = bal or 0
        fr.balance_after_wei = bal or 0
        if (bal or 0) >= threshold_wei:
            fr.status = "skipped"
            results.append(fr)
            continue
        if dry_run:
            fr.status = "skipped"
            results.append(fr)
            continue
        if not cast or not pk or not rpc:
            fr.status = "failed"
            fr.error = "missing cast/DEPLOYER_PK/SEPOLIA_RPC_URL"
            results.append(fr)
            continue
        try:
            out = subprocess.run(
                [cast, "send", w.address,
                 "--value", str(amount_wei),
                 "--private-key", pk,
                 "--rpc-url", rpc,
                 "--json"],
                check=False, capture_output=True, text=True, timeout=180,
            )
        except (subprocess.SubprocessError, OSError) as exc:
            fr.status = "failed"
            fr.error = mask_secrets_in_text(str(exc), [pk])
            results.append(fr)
            continue
        if out.returncode != 0:
            fr.status = "failed"
            fr.error = mask_secrets_in_text((out.stderr or out.stdout or "").strip(), [pk])
            results.append(fr)
            continue
        try:
            receipt = json.loads(out.stdout or "{}")
        except json.JSONDecodeError:
            fr.status = "failed"
            fr.error = "malformed cast output"
            results.append(fr)
            continue
        tx = str(receipt.get("transactionHash") or "").strip()
        if not tx:
            fr.status = "failed"
            fr.error = "no transactionHash in funding receipt"
            results.append(fr)
            continue
        fr.tx_hash = tx
        fr.explorer_url = etherscan_tx(SEPOLIA_CHAIN_ID, tx) or ""
        fr.funded_wei = amount_wei
        fr.status = "funded"
        bal_after = get_balance_wei(w.address, env)
        if bal_after is not None:
            fr.balance_after_wei = bal_after
        results.append(fr)
    return results


# ---------------------------------------------------------------- live preconditions

@dataclass(frozen=True)
class LivePrecheck:
    ok: bool
    errors: tuple[str, ...]
    warnings: tuple[str, ...]
    insufficient_voters: tuple[str, ...]    # member addresses below threshold


def check_live_preconditions(
    *,
    env: Mapping[str, str],
    registry: OnchainRegistry | None,
    wallets: Sequence[SandboxWalletRecord],
    voter_threshold_wei: int = 5 * 10**14,    # 0.0005 ETH per voter — enough for one cast
    operator_threshold_wei: int = 10 * 10**15,  # 0.01 ETH
    check_balances: bool = True,
) -> LivePrecheck:
    """Run all gates that must pass before a live broadcast.

    The voter balance check is best-effort — if ``cast`` isn't on PATH or
    RPC isn't set we already fail earlier in the env check, so balance
    failures here are skipped silently.
    """
    errors: list[str] = []
    warnings: list[str] = []

    env_check = check_env(env)
    if not env_check.ok:
        errors.append(env_check.error)

    reg_check = check_registry(registry)
    if not reg_check.ok:
        errors.append("required Sepolia contracts missing: "
                      + ", ".join(reg_check.missing_required))
    elif not reg_check.on_sepolia:
        warnings.append("registry chain_id is not 11155111 (Sepolia)")

    if not wallets:
        errors.append("sandbox wallets not generated yet")

    insufficient: list[str] = []
    if check_balances and env_check.ok and wallets:
        for w in wallets:
            bal = get_balance_wei(w.address, env)
            if bal is None:
                continue
            if bal < voter_threshold_wei:
                insufficient.append(w.address)
        if insufficient:
            errors.append(
                f"{len(insufficient)} sandbox member wallet(s) below funding threshold; "
                "fund them before live broadcast"
            )

    return LivePrecheck(
        ok=not errors,
        errors=tuple(errors),
        warnings=tuple(warnings),
        insufficient_voters=tuple(insufficient),
    )


def run_step(step: StepResult, ctx: RunContext) -> StepResult:
    """Execute a single step. Returns the updated ``StepResult``.

    Per-invocation idempotent reverts (e.g. AlreadyRegistered) are skipped
    and the loop continues. Only unknown errors abort the step.
    """
    step.mode = ctx.mode_label
    step.run_id = ctx.run_id
    invocations = _plan_step(step, ctx)
    if not invocations:
        step.status = "skipped"
        step.note = "nothing to do (no contract address or empty roster)"
        return step

    # Pre-step timing waits (live only) — ballot windows must be open/closed.
    if not ctx.dry_run:
        if step.key == "ballot_votes" and ctx.ballot_opens_at > 0:
            wait = ctx.ballot_opens_at - int(time.time()) + 3
            if wait > 0:
                time.sleep(min(wait, 300))
        elif step.key == "ballot_finalize" and ctx.ballot_closes_at > 0:
            wait = ctx.ballot_closes_at - int(time.time()) + 3
            if wait > 0:
                time.sleep(min(wait, 300))

    last_hash = ""
    last_member = ""
    total_gas = 0
    success_count = 0
    skipped_count = 0
    fatal_error = ""
    fatal_hash = ""
    fatal_member = ""

    for inv in invocations:
        res = _execute_invocation(inv, ctx)
        if res.ok:
            success_count += 1
            last_hash = res.tx_hash
            total_gas += res.gas_used
            last_member = inv.member_wallet or last_member
            if ctx.sleep_between:
                time.sleep(ctx.sleep_between)
        elif _is_idempotent_revert(res.error):
            # Already on-chain — treat this invocation as a safe skip.
            skipped_count += 1
        else:
            fatal_error = _plain_error(res.error)
            fatal_hash = res.tx_hash or last_hash
            fatal_member = inv.member_wallet
            break

    # After a successful live ballot_create, resolve the actual ballot ID.
    if step.key == "ballot_create" and success_count > 0 and not ctx.dry_run:
        ballot_addr = ctx.registry.address_of("InvestmentPolicyBallot") or ""
        raw = _cast_call(ballot_addr, "ballotCount()(uint256)", [], ctx.env)
        if raw:
            try:
                count = int(raw.strip())
                if count > 0:
                    ctx.ballot_id = count - 1
            except ValueError:
                pass

    step.gas_used = total_gas
    step.member_wallet = last_member or step.member_wallet

    if fatal_error:
        # At least one invocation failed with an unknown error.
        step.tx_hash = fatal_hash or last_hash
        step.member_wallet = fatal_member or step.member_wallet
        step.error = fatal_error
        step.status = "failed"
        if not ctx.dry_run:
            step.explorer_url = etherscan_tx(SEPOLIA_CHAIN_ID, step.tx_hash) or ""
        return step

    step.tx_hash = last_hash
    if ctx.dry_run:
        step.explorer_url = ""
        if success_count == 0 and skipped_count > 0:
            step.status = "skipped_existing"
            step.note = "all invocations already recorded on-chain (dry-run)"
        else:
            step.status = "simulated"
    else:
        step.explorer_url = etherscan_tx(SEPOLIA_CHAIN_ID, last_hash) or ""
        if success_count == 0 and skipped_count > 0:
            step.status = "skipped_existing"
            step.note = "all invocations already recorded on-chain"
        else:
            step.status = "confirmed"
    return step


_SOFT_FAIL_STEPS: frozenset[str] = frozenset({"ballot_votes", "ballot_finalize"})


def run_full_sandbox_sepolia_demo(ctx: RunContext) -> list[StepResult]:
    """Run every step in canonical order. Stops on first hard failure but
    preserves earlier confirmed/skipped_existing tx links.
    Idempotent on-chain skips (``skipped_existing``) do NOT stop the run.
    Soft-fail steps (ballot_votes, ballot_finalize) do not stop the run so
    the actuarial proof step always executes regardless of ballot outcome.
    """
    steps = empty_steps()
    for step in steps:
        run_step(step, ctx)
        if step.status == "failed" and step.key not in _SOFT_FAIL_STEPS:
            break
    return steps


# ---------------------------------------------------------------- UI shaping

def member_roster_rows(
    wallets: Sequence[SandboxWalletRecord],
    steps: Sequence[StepResult] | None = None,
) -> list[dict]:
    """Per-member roster row with Etherscan deep-links and per-step tx links."""
    by_member_step: dict[tuple[str, str], StepResult] = {}
    if steps:
        for s in steps:
            if s.member_wallet:
                by_member_step[(s.member_wallet.lower(), s.key)] = s

    out = []
    for w in wallets:
        addr = w.address
        row = {
            "label": w.label,
            "cohort": w.cohort,
            "age": w.age,
            "address": addr,
            "address_short": (addr[:6] + "…" + addr[-4:]) if len(addr) >= 10 else addr,
            "address_url": etherscan_address(SEPOLIA_CHAIN_ID, addr) or "",
            "registered_url": "",
            "contribution_url": "",
            "retirement_url": "",
            "vote_url": "",
        }
        if steps:
            for k, ui_field in (
                ("register_members", "registered_url"),
                ("post_contributions", "contribution_url"),
                ("open_retirement", "retirement_url"),
                ("ballot_votes", "vote_url"),
            ):
                hit = by_member_step.get((addr.lower(), k))
                if hit and hit.explorer_url:
                    row[ui_field] = hit.explorer_url
        out.append(row)
    return out


def step_rows_for_ui(steps: Sequence[StepResult]) -> list[dict]:
    rows = []
    for i, s in enumerate(steps, start=1):
        rows.append({
            "step": i,
            "key": s.key,
            "label": s.label,
            "contract": s.contract,
            "function": s.function,
            "actor": s.actor,
            "member_wallet": s.member_wallet,
            "tx_hash": s.tx_hash,
            "short_hash": (s.tx_hash[:10] + "…") if s.tx_hash else "",
            "explorer_url": s.explorer_url,
            "status": s.status,
            "error": s.error,
        })
    return rows


def etherscan_story_flat_rows(steps: Sequence[StepResult]) -> list[dict]:
    """Flattened, Reflex-foreach-friendly rows for the Etherscan story.

    Avoids a nested ``rx.foreach`` (which Reflex cannot type-check on
    ``list[dict]``) by emitting one row per heading and one per link, with
    a ``row_type`` discriminator.
    """
    out: list[dict] = []
    for group in etherscan_story_groups(steps):
        out.append({
            "row_type": "header",
            "title": group["title"],
            "label": "",
            "url": "",
            "status": "",
            "has_items": "yes" if group["items"] else "no",
        })
        for item in group["items"]:
            out.append({
                "row_type": "item",
                "title": group["title"],
                "label": item["label"],
                "url": item["url"],
                "status": item["status"],
                "has_items": "yes",
            })
        if not group["items"]:
            out.append({
                "row_type": "empty",
                "title": group["title"],
                "label": "No confirmed transactions yet.",
                "url": "",
                "status": "",
                "has_items": "no",
            })
    return out


def etherscan_story_groups(steps: Sequence[StepResult]) -> list[dict]:
    """Group confirmed steps for the presentation-friendly Etherscan section."""
    groups = [
        ("Member lifecycle", ("register_members", "publish_piu_price", "post_contributions", "open_retirement")),
        ("Fairness governance", ("fairness_baseline", "fairness_proposal_pass", "fairness_proposal_fail")),
        ("Investment governance", ("ballot_create", "ballot_weights", "ballot_votes", "ballot_finalize")),
        ("Actuarial proof", ("actuarial_publish",)),
    ]
    by_key = {s.key: s for s in steps}
    out = []
    for title, keys in groups:
        items = []
        for k in keys:
            s = by_key.get(k)
            if s and s.explorer_url:
                items.append({
                    "label": STEP_LABELS.get(k, k),
                    "url": s.explorer_url,
                    "status": s.status,
                })
        out.append({"title": title, "items": items})
    return out


__all__ = [
    "REQUIRED_CONTRACTS",
    "OPTIONAL_CONTRACTS",
    "STEP_ORDER",
    "STEP_SIGNERS",
    "STEP_TARGETS",
    "STEP_LABELS",
    "EnvCheck",
    "RegistryCheck",
    "StepResult",
    "RunContext",
    "CastInvocation",
    "check_env",
    "check_registry",
    "empty_steps",
    "run_step",
    "run_full_sandbox_sepolia_demo",
    "member_roster_rows",
    "step_rows_for_ui",
    "etherscan_story_groups",
    "etherscan_story_flat_rows",
    "check_live_preconditions",
    "fund_sandbox_wallets",
    "_is_idempotent_revert",
    "_plain_error",
    "FundingResult",
    "LivePrecheck",
    "get_balance_wei",
]
