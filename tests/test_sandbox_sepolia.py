"""Tests for the sandbox Sepolia proof flow."""
from __future__ import annotations

from pathlib import Path

import pytest

from engine.onchain_registry import (
    SEPOLIA_CHAIN_ID,
    ContractRecord,
    OnchainRegistry,
    etherscan_tx,
)
from engine.sandbox_sepolia import (
    OPTIONAL_CONTRACTS,
    REQUIRED_CONTRACTS,
    STEP_ORDER,
    STEP_SIGNERS,
    CastInvocation,
    RunContext,
    StepResult,
    check_env,
    check_registry,
    empty_steps,
    etherscan_story_groups,
    member_roster_rows,
    run_full_sandbox_sepolia_demo,
    run_step,
    step_rows_for_ui,
    _is_idempotent_revert,
)
from engine.sandbox_wallets import SandboxWalletRecord


# ----- helpers --------------------------------------------------------------

def _addr(byte_val: int) -> str:
    return "0x" + (f"{byte_val:02x}" * 20)


def _pk(byte_val: int) -> str:
    return "0x" + (f"{byte_val:02x}" * 32)


def _wallets() -> list[SandboxWalletRecord]:
    return [
        SandboxWalletRecord("Sandbox A — near retiree", 1960, 65, "near_retiree", _addr(0xa0), _pk(0xa0)),
        SandboxWalletRecord("Sandbox B — late career", 1965, 60, "active",       _addr(0xb0), _pk(0xb0)),
        SandboxWalletRecord("Sandbox C — mid career",  1970, 55, "active",       _addr(0xc0), _pk(0xc0)),
        SandboxWalletRecord("Sandbox D — mid career",  1980, 45, "active",       _addr(0xd0), _pk(0xd0)),
        SandboxWalletRecord("Sandbox E — early career",1990, 35, "young",        _addr(0xe0), _pk(0xe0)),
        SandboxWalletRecord("Sandbox F — entry level", 2000, 25, "young",        _addr(0xf0), _pk(0xf0)),
    ]


def _registry(complete: bool = True) -> OnchainRegistry:
    contracts = {}
    names = list(REQUIRED_CONTRACTS)
    if complete:
        names += list(OPTIONAL_CONTRACTS)
    for i, name in enumerate(names):
        contracts[name] = ContractRecord(
            name=name, address=_addr(0x10 + i), tx_hash="", verified=True,
        )
    return OnchainRegistry(
        chain_id=SEPOLIA_CHAIN_ID, chain_name="Sepolia Testnet",
        deployer=_addr(0x01), deployed_at="", explorer_base="https://sepolia.etherscan.io",
        rpc_hint="", verified=True, contracts=contracts,
        source_path="<test>", raw={},
    )


# ----- env / registry -------------------------------------------------------

def test_check_env_reports_missing_keys_clearly():
    res = check_env({})
    assert not res.ok
    assert "SEPOLIA_RPC_URL" in res.error
    assert "DEPLOYER_PK" in res.error


def test_check_env_passes_with_required_vars(monkeypatch):
    # cast may not be on PATH in CI; fake it.
    res = check_env({
        "SEPOLIA_RPC_URL": "https://rpc",
        "DEPLOYER_PK": "0x" + "ab" * 32,
        "AEQUITAS_DEVTOOLS": "1",
    })
    # cast may legitimately be missing — verify env-only fields independently.
    assert res.deployer_pk_present
    assert res.devtools_enabled
    assert res.rpc_url == "https://rpc"


def test_check_registry_flags_missing_required_contracts():
    res = check_registry(None)
    assert not res.ok
    assert set(res.missing_required) == set(REQUIRED_CONTRACTS)


def test_check_registry_passes_when_required_present():
    reg = _registry(complete=True)
    res = check_registry(reg)
    assert res.ok
    assert res.missing_required == ()
    assert res.on_sepolia is True


# ----- step ordering --------------------------------------------------------

def test_empty_steps_in_canonical_order():
    steps = empty_steps()
    assert [s.key for s in steps] == list(STEP_ORDER)


def test_only_castvote_requires_member_signature():
    member_keys = [k for k, v in STEP_SIGNERS.items() if v == "member"]
    assert member_keys == ["ballot_votes"]


# ----- runner (dry-run) -----------------------------------------------------

def test_full_demo_runs_in_order_and_records_etherscan_links():
    ctx = RunContext(
        env={"SEPOLIA_RPC_URL": "https://rpc", "DEPLOYER_PK": _pk(0x01),
             "AEQUITAS_DEVTOOLS": "1"},
        registry=_registry(),
        wallets=_wallets(),
        dry_run=True,
    )
    results = run_full_sandbox_sepolia_demo(ctx)
    keys = [s.key for s in results]
    assert keys == list(STEP_ORDER)
    # Dry-run never produces a real on-chain tx, so no explorer URL.
    for s in results:
        assert s.explorer_url == ""
        assert s.mode == "dry_run"
    # The full-demo dry run produces a simulated/skipped status across all steps.
    assert all(s.status in ("simulated", "skipped", "skipped_existing") for s in results)


def test_run_skips_actuarial_when_optional_contracts_missing():
    ctx = RunContext(
        env={"SEPOLIA_RPC_URL": "rpc", "DEPLOYER_PK": _pk(1), "AEQUITAS_DEVTOOLS": "1"},
        registry=_registry(complete=False),
        wallets=_wallets(),
        dry_run=True,
    )
    results = run_full_sandbox_sepolia_demo(ctx)
    actuarial = next(s for s in results if s.key == "actuarial_publish")
    assert actuarial.status == "skipped"


def test_member_roster_rows_link_to_per_step_tx():
    wallets = _wallets()
    steps = empty_steps()
    # Mark one member as having registered.
    target = wallets[0].address
    for s in steps:
        if s.key == "register_members":
            s.status = "confirmed"
            s.tx_hash = "0x" + "11" * 32
            s.explorer_url = etherscan_tx(SEPOLIA_CHAIN_ID, s.tx_hash) or ""
            s.member_wallet = target

    rows = member_roster_rows(wallets, steps)
    target_row = next(r for r in rows if r["address"] == target)
    assert target_row["registered_url"].startswith("https://sepolia.etherscan.io/tx/")


def test_step_rows_for_ui_shape():
    rows = step_rows_for_ui(empty_steps())
    assert rows[0]["step"] == 1
    assert "label" in rows[0]
    assert "actor" in rows[0]


def test_etherscan_story_groups_have_required_titles():
    titles = [g["title"] for g in etherscan_story_groups(empty_steps())]
    assert "Member lifecycle" in titles
    assert "Fairness governance" in titles
    assert "Investment governance" in titles
    assert "Actuarial proof" in titles


def test_dry_run_never_calls_subprocess(monkeypatch):
    """Dry-run path must not invoke ``subprocess.run`` for any step."""
    import engine.sandbox_sepolia as sbx
    called = {"n": 0}

    def boom(*a, **kw):
        called["n"] += 1
        raise AssertionError("subprocess.run called in dry_run")

    monkeypatch.setattr(sbx.subprocess, "run", boom)
    ctx = RunContext(
        env={"SEPOLIA_RPC_URL": "rpc", "DEPLOYER_PK": _pk(1), "AEQUITAS_DEVTOOLS": "1"},
        registry=_registry(), wallets=_wallets(), dry_run=True,
    )
    sbx.run_full_sandbox_sepolia_demo(ctx)
    assert called["n"] == 0


def test_live_member_step_uses_member_private_key(monkeypatch):
    """The member-signed castVote step must sign with the member key, not DEPLOYER_PK."""
    import engine.sandbox_sepolia as sbx

    captured: list[dict] = []

    class _FakeProc:
        returncode = 0
        stdout = '{"transactionHash":"0x' + ("ab" * 32) + '","status":"0x1","gasUsed":"0x5208"}'
        stderr = ""

    def fake_run(cmd, **kw):
        captured.append({"cmd": list(cmd)})
        return _FakeProc()

    monkeypatch.setattr(sbx.subprocess, "run", fake_run)
    monkeypatch.setattr(sbx.shutil, "which", lambda x: "/usr/bin/cast")

    wallets = _wallets()
    member_keys = {w.address.lower(): w.private_key for w in wallets}
    deployer = _pk(0xee)
    ctx = RunContext(
        env={"SEPOLIA_RPC_URL": "rpc", "DEPLOYER_PK": deployer, "AEQUITAS_DEVTOOLS": "1"},
        registry=_registry(), wallets=wallets, dry_run=False,
    )
    # Run only the vote step.
    vote = next(s for s in sbx.empty_steps() if s.key == "ballot_votes")
    sbx.run_step(vote, ctx)

    member_pks_seen = set()
    for entry in captured:
        cmd = entry["cmd"]
        if "--private-key" in cmd:
            pk = cmd[cmd.index("--private-key") + 1]
            assert pk != deployer, "castVote must not use DEPLOYER_PK"
            member_pks_seen.add(pk.lower())
    assert member_pks_seen.issubset(set(member_keys.values()))
    assert len(captured) == len(wallets)  # one cast per voter


def test_live_operator_step_uses_deployer_pk(monkeypatch):
    import engine.sandbox_sepolia as sbx

    captured: list[list[str]] = []

    class _FakeProc:
        returncode = 0
        stdout = '{"transactionHash":"0x' + ("cd" * 32) + '","status":"0x1","gasUsed":"0x5208"}'
        stderr = ""

    monkeypatch.setattr(sbx.subprocess, "run",
                        lambda cmd, **kw: (captured.append(list(cmd)) or _FakeProc()))
    monkeypatch.setattr(sbx.shutil, "which", lambda x: "/usr/bin/cast")

    deployer = _pk(0x44)
    ctx = RunContext(
        env={"SEPOLIA_RPC_URL": "rpc", "DEPLOYER_PK": deployer, "AEQUITAS_DEVTOOLS": "1"},
        registry=_registry(), wallets=_wallets(), dry_run=False,
    )
    step = next(s for s in sbx.empty_steps() if s.key == "publish_piu_price")
    sbx.run_step(step, ctx)
    assert captured, "expected at least one cast invocation"
    cmd = captured[0]
    assert cmd[cmd.index("--private-key") + 1] == deployer


def test_live_status_yields_etherscan_url(monkeypatch):
    import engine.sandbox_sepolia as sbx

    tx = "0x" + ("99" * 32)

    class _FakeProc:
        returncode = 0
        stdout = '{"transactionHash":"' + tx + '","status":"0x1","gasUsed":"0x5208"}'
        stderr = ""

    monkeypatch.setattr(sbx.subprocess, "run", lambda *a, **kw: _FakeProc())
    monkeypatch.setattr(sbx.shutil, "which", lambda x: "/usr/bin/cast")

    ctx = RunContext(
        env={"SEPOLIA_RPC_URL": "rpc", "DEPLOYER_PK": _pk(1), "AEQUITAS_DEVTOOLS": "1"},
        registry=_registry(), wallets=_wallets(), dry_run=False,
    )
    step = next(s for s in sbx.empty_steps() if s.key == "publish_piu_price")
    sbx.run_step(step, ctx)
    assert step.status == "confirmed"
    assert step.explorer_url.startswith("https://sepolia.etherscan.io/tx/")
    assert step.tx_hash == tx


def test_funding_skips_already_funded(monkeypatch):
    import engine.sandbox_sepolia as sbx
    monkeypatch.setattr(sbx, "get_balance_wei", lambda addr, env: 10**18)
    sent = []
    monkeypatch.setattr(sbx.subprocess, "run",
                        lambda cmd, **kw: sent.append(cmd) or None)
    monkeypatch.setattr(sbx.shutil, "which", lambda x: "/usr/bin/cast")
    results = sbx.fund_sandbox_wallets(
        _wallets(),
        env={"SEPOLIA_RPC_URL": "rpc", "DEPLOYER_PK": _pk(1)},
        threshold_wei=5 * 10**14, amount_wei=10**15, dry_run=False,
    )
    assert sent == []  # nothing was sent — all wallets already funded
    assert all(r.status == "skipped" for r in results)


def test_funding_dry_run_does_not_call_cast_send(monkeypatch):
    import engine.sandbox_sepolia as sbx
    monkeypatch.setattr(sbx, "get_balance_wei", lambda addr, env: 0)
    boom_calls = {"n": 0}
    def boom(*a, **kw):
        boom_calls["n"] += 1
        raise AssertionError("cast send invoked in dry-run funding")
    monkeypatch.setattr(sbx.subprocess, "run", boom)
    monkeypatch.setattr(sbx.shutil, "which", lambda x: "/usr/bin/cast")
    results = sbx.fund_sandbox_wallets(
        _wallets(),
        env={"SEPOLIA_RPC_URL": "rpc", "DEPLOYER_PK": _pk(1)},
        threshold_wei=10**18, amount_wei=10**15, dry_run=True,
    )
    assert boom_calls["n"] == 0
    assert all(r.status in ("skipped",) for r in results)


def test_live_precheck_fails_without_env(monkeypatch):
    import engine.sandbox_sepolia as sbx
    pre = sbx.check_live_preconditions(
        env={}, registry=_registry(), wallets=_wallets(), check_balances=False,
    )
    assert not pre.ok
    assert any("SEPOLIA_RPC_URL" in e or "DEPLOYER_PK" in e or "cast" in e
               for e in pre.errors)


def test_etherscan_story_flat_rows_has_header_and_items():
    import engine.sandbox_sepolia as sbx
    steps = sbx.empty_steps()
    # Mark one step confirmed with an explorer URL.
    target = next(s for s in steps if s.key == "register_members")
    target.status = "confirmed"
    target.explorer_url = "https://sepolia.etherscan.io/tx/0xabc"
    rows = sbx.etherscan_story_flat_rows(steps)
    types = {r["row_type"] for r in rows}
    assert "header" in types
    assert "item" in types or "empty" in types
    # No row should accidentally embed a private key shape.
    import re, json
    blob = json.dumps(rows)
    assert not re.search(r"0x[0-9a-fA-F]{64}", blob)


def test_castinvocation_cmd_preview_redacts_private_key():
    inv = CastInvocation(
        contract="CohortLedger", contract_address=_addr(0x10), function="registerMember",
        args=[_addr(0xa0), "1960"], actor="operator", signer_address=_addr(0x01),
    )
    cmd = inv.cmd_preview(mask_pk=True)
    blob = " ".join(cmd)
    assert "[REDACTED]" in blob
    # Make sure no 64-hex private key sneaks in.
    import re
    assert not re.search(r"0x[0-9a-fA-F]{64}", blob)


# ----- idempotent-revert handling -------------------------------------------

def test_is_idempotent_revert_matches_already_registered():
    assert _is_idempotent_revert("execution reverted: AlreadyRegistered(0xabc)")
    assert _is_idempotent_revert("AlreadyRegistered(0x1234)")
    assert _is_idempotent_revert("Error: already registered")


def test_is_idempotent_revert_does_not_match_unknown_errors():
    assert not _is_idempotent_revert("InsufficientAssets(1000000000000000000, 0)")
    assert not _is_idempotent_revert("execution reverted: NotRegistered(0xabc)")
    assert not _is_idempotent_revert("out of gas")
    assert not _is_idempotent_revert("")


def test_already_registered_treated_as_skipped_existing(monkeypatch):
    """If registerMember reverts with AlreadyRegistered, the step becomes skipped_existing."""
    import engine.sandbox_sepolia as sbx

    class _AlreadyFail:
        returncode = 1
        stdout = ""
        stderr = "Error: AlreadyRegistered(0xa0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0)"

    monkeypatch.setattr(sbx.subprocess, "run", lambda *a, **kw: _AlreadyFail())
    monkeypatch.setattr(sbx.shutil, "which", lambda x: "/usr/bin/cast")

    ctx = RunContext(
        env={"SEPOLIA_RPC_URL": "rpc", "DEPLOYER_PK": _pk(1), "AEQUITAS_DEVTOOLS": "1"},
        registry=_registry(), wallets=_wallets(), dry_run=False,
    )
    step = next(s for s in sbx.empty_steps() if s.key == "register_members")
    sbx.run_step(step, ctx)
    assert step.status == "skipped_existing"
    assert step.error == ""     # not an error — expected idempotent skip


def test_unknown_register_error_still_fails(monkeypatch):
    """An unknown revert (not AlreadyRegistered) must still produce a failed step."""
    import engine.sandbox_sepolia as sbx

    class _UnknownFail:
        returncode = 1
        stdout = ""
        stderr = "Error: out of gas"

    monkeypatch.setattr(sbx.subprocess, "run", lambda *a, **kw: _UnknownFail())
    monkeypatch.setattr(sbx.shutil, "which", lambda x: "/usr/bin/cast")

    ctx = RunContext(
        env={"SEPOLIA_RPC_URL": "rpc", "DEPLOYER_PK": _pk(1), "AEQUITAS_DEVTOOLS": "1"},
        registry=_registry(), wallets=_wallets(), dry_run=False,
    )
    step = next(s for s in sbx.empty_steps() if s.key == "register_members")
    sbx.run_step(step, ctx)
    assert step.status == "failed"
    assert step.error != ""


def test_full_demo_continues_after_already_registered(monkeypatch):
    """Full demo must not stop if register_members gets AlreadyRegistered."""
    import engine.sandbox_sepolia as sbx

    tx = "0x" + ("ee" * 32)

    class _AlreadyFail:
        returncode = 1; stdout = ""; stderr = "AlreadyRegistered(0x1)"

    class _Ok:
        returncode = 0
        stdout = '{"transactionHash":"' + tx + '","status":"0x1","gasUsed":"0x5208"}'
        stderr = ""

    call_count = {"n": 0}

    def fake_run(cmd, **kw):
        call_count["n"] += 1
        # First batch (register_members) always fails with AlreadyRegistered.
        # All subsequent calls succeed.
        if "registerMember" in " ".join(cmd):
            return _AlreadyFail()
        return _Ok()

    monkeypatch.setattr(sbx.subprocess, "run", fake_run)
    monkeypatch.setattr(sbx.shutil, "which", lambda x: "/usr/bin/cast")

    ctx = RunContext(
        env={"SEPOLIA_RPC_URL": "rpc", "DEPLOYER_PK": _pk(1), "AEQUITAS_DEVTOOLS": "1"},
        registry=_registry(), wallets=_wallets(), dry_run=False,
    )
    results = sbx.run_full_sandbox_sepolia_demo(ctx)
    reg = next(s for s in results if s.key == "register_members")
    assert reg.status == "skipped_existing"
    # Demo must have continued past register_members.
    later = [s for s in results if s.key not in ("register_members", "actuarial_publish")]
    assert any(s.status == "confirmed" for s in later), (
        f"expected later steps confirmed, got {[(s.key, s.status) for s in later]}"
    )


# ----- fund_protocol_pool step ----------------------------------------------

def test_fund_protocol_pool_in_step_order():
    """fund_protocol_pool must appear after post_contributions and before open_retirement."""
    order = list(STEP_ORDER)
    assert "fund_protocol_pool" in order
    assert order.index("fund_protocol_pool") > order.index("post_contributions")
    assert order.index("fund_protocol_pool") < order.index("open_retirement")


def test_fund_protocol_pool_uses_value_wei(monkeypatch):
    """The fund_protocol_pool step must invoke cast send with --value."""
    import engine.sandbox_sepolia as sbx

    cmds_seen: list[list[str]] = []

    class _Ok:
        returncode = 0
        stdout = '{"transactionHash":"0x' + ("cc" * 32) + '","status":"0x1","gasUsed":"0x5208"}'
        stderr = ""

    monkeypatch.setattr(sbx.subprocess, "run",
                        lambda cmd, **kw: cmds_seen.append(list(cmd)) or _Ok())
    monkeypatch.setattr(sbx.shutil, "which", lambda x: "/usr/bin/cast")

    ctx = RunContext(
        env={"SEPOLIA_RPC_URL": "rpc", "DEPLOYER_PK": _pk(1), "AEQUITAS_DEVTOOLS": "1"},
        registry=_registry(), wallets=_wallets(), dry_run=False,
    )
    step = next(s for s in sbx.empty_steps() if s.key == "fund_protocol_pool")
    sbx.run_step(step, ctx)
    assert step.status == "confirmed"
    assert cmds_seen, "expected at least one cast invocation"
    cmd = cmds_seen[0]
    assert "--value" in cmd, "fund_protocol_pool must pass --value to cast send"
    val_idx = cmd.index("--value")
    assert int(cmd[val_idx + 1]) > 0


def test_insufficient_assets_produces_readable_error(monkeypatch):
    """InsufficientAssets revert must be translated into a plain-English message."""
    import engine.sandbox_sepolia as sbx

    class _InsufficientFail:
        returncode = 1
        stdout = ""
        stderr = "Error: InsufficientAssets(1000000000000000000, 0)"

    monkeypatch.setattr(sbx.subprocess, "run", lambda *a, **kw: _InsufficientFail())
    monkeypatch.setattr(sbx.shutil, "which", lambda x: "/usr/bin/cast")

    ctx = RunContext(
        env={"SEPOLIA_RPC_URL": "rpc", "DEPLOYER_PK": _pk(1), "AEQUITAS_DEVTOOLS": "1"},
        registry=_registry(), wallets=_wallets(), dry_run=False,
    )
    step = next(s for s in sbx.empty_steps() if s.key == "open_retirement")
    sbx.run_step(step, ctx)
    assert step.status == "failed"
    assert "protocol pool" in step.error.lower() or "insufficient" in step.error.lower()


def test_castinvocation_value_wei_in_cmd_preview():
    """CastInvocation with value_wei must include --value in preview."""
    inv = CastInvocation(
        contract="LongevaPool", contract_address=_addr(0x20), function="simulateYield()",
        args=[], actor="operator", signer_address=_addr(0x01),
        value_wei=2_000_000_000_000_000,
    )
    cmd = inv.cmd_preview(mask_pk=True)
    assert "--value" in cmd
    assert "2000000000000000" in cmd


# ----- Phase 3: ballot timing, tracking, and actuarial proof ----------------

def test_ballot_create_timestamps_are_ordered():
    """Dry-run ballot_create must produce opens < closes, stored on ctx."""
    import engine.sandbox_sepolia as sbx
    ctx = RunContext(
        env={"SEPOLIA_RPC_URL": "rpc", "DEPLOYER_PK": _pk(1), "AEQUITAS_DEVTOOLS": "1"},
        registry=_registry(), wallets=_wallets(), dry_run=True,
    )
    step = next(s for s in sbx.empty_steps() if s.key == "ballot_create")
    invs = sbx._plan_step(step, ctx)
    assert len(invs) == 1
    args = invs[0].args
    opens_at = int(args[3])
    closes_at = int(args[4])
    assert opens_at < closes_at, "opensAt must be before closesAt"
    assert ctx.ballot_opens_at == opens_at
    assert ctx.ballot_closes_at == closes_at


def test_ballot_weights_plan_uses_ctx_ballot_id():
    """ballot_weights plan must pass ctx.ballot_id as first argument."""
    import engine.sandbox_sepolia as sbx
    ctx = RunContext(
        env={"SEPOLIA_RPC_URL": "rpc", "DEPLOYER_PK": _pk(1), "AEQUITAS_DEVTOOLS": "1"},
        registry=_registry(), wallets=_wallets(), dry_run=True,
        ballot_id=7,
    )
    step = next(s for s in sbx.empty_steps() if s.key == "ballot_weights")
    invs = sbx._plan_step(step, ctx)
    assert len(invs) == 1
    assert invs[0].args[0] == "7"


def test_already_voted_treated_as_skipped_existing(monkeypatch):
    """AlreadyVoted revert on castVote must produce skipped_existing, not failed."""
    import engine.sandbox_sepolia as sbx

    class _AlreadyVoted:
        returncode = 1
        stdout = ""
        stderr = "Error: AlreadyVoted()"

    monkeypatch.setattr(sbx.subprocess, "run", lambda *a, **kw: _AlreadyVoted())
    monkeypatch.setattr(sbx.shutil, "which", lambda x: "/usr/bin/cast")

    ctx = RunContext(
        env={"SEPOLIA_RPC_URL": "rpc", "DEPLOYER_PK": _pk(1), "AEQUITAS_DEVTOOLS": "1"},
        registry=_registry(), wallets=_wallets(), dry_run=False,
    )
    step = next(s for s in sbx.empty_steps() if s.key == "ballot_votes")
    sbx.run_step(step, ctx)
    assert step.status == "skipped_existing"
    assert step.error == ""


def test_ballot_already_finalized_treated_as_skipped_existing(monkeypatch):
    """BallotAlreadyFinalized on finalizeBallot must produce skipped_existing."""
    import engine.sandbox_sepolia as sbx

    class _AlreadyFinalized:
        returncode = 1
        stdout = ""
        stderr = "Error: BallotAlreadyFinalized(0)"

    monkeypatch.setattr(sbx.subprocess, "run", lambda *a, **kw: _AlreadyFinalized())
    monkeypatch.setattr(sbx.shutil, "which", lambda x: "/usr/bin/cast")

    ctx = RunContext(
        env={"SEPOLIA_RPC_URL": "rpc", "DEPLOYER_PK": _pk(1), "AEQUITAS_DEVTOOLS": "1"},
        registry=_registry(), wallets=_wallets(), dry_run=False,
    )
    step = next(s for s in sbx.empty_steps() if s.key == "ballot_finalize")
    sbx.run_step(step, ctx)
    assert step.status == "skipped_existing"
    assert step.error == ""


def test_full_demo_continues_to_actuarial_after_ballot_failure(monkeypatch):
    """ballot_votes and ballot_finalize failures must not stop the run; actuarial must proceed."""
    import engine.sandbox_sepolia as sbx

    tx = "0x" + ("aa" * 32)

    class _BallotFail:
        returncode = 1
        stdout = ""
        stderr = "Error: IneligibleVoter(0xabc)"

    class _Ok:
        returncode = 0
        stdout = '{"transactionHash":"' + tx + '","status":"0x1","gasUsed":"0x5208"}'
        stderr = ""

    def fake_run(cmd, **kw):
        cmd_str = " ".join(cmd)
        if "castVote" in cmd_str or "finalizeBallot" in cmd_str:
            return _BallotFail()
        return _Ok()

    monkeypatch.setattr(sbx.subprocess, "run", fake_run)
    monkeypatch.setattr(sbx.shutil, "which", lambda x: "/usr/bin/cast")
    monkeypatch.setattr(sbx, "_cast_call", lambda *a, **kw: "1")

    ctx = RunContext(
        env={"SEPOLIA_RPC_URL": "rpc", "DEPLOYER_PK": _pk(1), "AEQUITAS_DEVTOOLS": "1"},
        registry=_registry(), wallets=_wallets(), dry_run=False,
    )
    results = sbx.run_full_sandbox_sepolia_demo(ctx)
    votes = next(s for s in results if s.key == "ballot_votes")
    assert votes.status == "failed"
    actuarial = next(s for s in results if s.key == "actuarial_publish")
    assert actuarial.status != "not_run", (
        f"actuarial_publish should have run after ballot failure, got {actuarial.status}"
    )


def test_actuarial_publish_uses_nonzero_keys():
    """actuarial_publish must produce 10 non-zero, deterministic 32-byte keys."""
    import engine.sandbox_sepolia as sbx
    ctx = RunContext(
        env={"SEPOLIA_RPC_URL": "rpc", "DEPLOYER_PK": _pk(1), "AEQUITAS_DEVTOOLS": "1"},
        registry=_registry(), wallets=_wallets(), dry_run=True,
        run_id="test_run_001",
    )
    step = next(s for s in sbx.empty_steps() if s.key == "actuarial_publish")
    invs = sbx._plan_step(step, ctx)
    assert len(invs) == 1
    args = invs[0].args
    assert len(args) == 10
    for arg in args:
        assert arg.startswith("0x"), f"key must be 0x-prefixed: {arg}"
        assert len(arg) == 66, f"key must be 32 bytes (66 chars with 0x): {arg}"
        assert arg != "0x" + "00" * 32, f"key must be non-zero: {arg}"


def test_actuarial_publish_skipped_when_optional_contracts_missing():
    """actuarial_publish must be skipped when ActuarialResultRegistry is not deployed."""
    import engine.sandbox_sepolia as sbx
    ctx = RunContext(
        env={"SEPOLIA_RPC_URL": "rpc", "DEPLOYER_PK": _pk(1), "AEQUITAS_DEVTOOLS": "1"},
        registry=_registry(complete=False), wallets=_wallets(), dry_run=True,
    )
    step = next(s for s in sbx.empty_steps() if s.key == "actuarial_publish")
    sbx.run_step(step, ctx)
    assert step.status == "skipped"


def test_ballot_create_live_updates_ballot_id(monkeypatch):
    """After a live ballot_create, ctx.ballot_id must be updated from ballotCount()."""
    import engine.sandbox_sepolia as sbx

    tx = "0x" + ("bb" * 32)

    class _Ok:
        returncode = 0
        stdout = '{"transactionHash":"' + tx + '","status":"0x1","gasUsed":"0x5208"}'
        stderr = ""

    monkeypatch.setattr(sbx.subprocess, "run", lambda *a, **kw: _Ok())
    monkeypatch.setattr(sbx.shutil, "which", lambda x: "/usr/bin/cast")
    monkeypatch.setattr(sbx, "_cast_call", lambda *a, **kw: "3")

    ctx = RunContext(
        env={"SEPOLIA_RPC_URL": "rpc", "DEPLOYER_PK": _pk(1), "AEQUITAS_DEVTOOLS": "1"},
        registry=_registry(), wallets=_wallets(), dry_run=False,
    )
    step = next(s for s in sbx.empty_steps() if s.key == "ballot_create")
    sbx.run_step(step, ctx)
    assert step.status == "confirmed"
    assert ctx.ballot_id == 2, f"expected ballot_id=2 (count=3), got {ctx.ballot_id}"


# ---- Phase 4: contribution + retirement idempotency -------------------------

def test_inactive_member_contribution_treated_as_skipped_existing(monkeypatch):
    """InactiveMember(address) — selector 0xf7476063 — must be skipped_existing,
    not fatal, so repeated post_contributions runs do not break the full demo."""
    import engine.sandbox_sepolia as sbx

    inactive_error = "execution reverted: InactiveMember(0xA0A0A0A0A0A0A0A0A0A0A0A0A0A0A0A0A0A0A0A0)"

    class _Fail:
        returncode = 1
        stdout = ""
        stderr = inactive_error

    monkeypatch.setattr(sbx.subprocess, "run", lambda *a, **kw: _Fail())
    monkeypatch.setattr(sbx.shutil, "which", lambda x: "/usr/bin/cast")

    ctx = RunContext(
        env={"SEPOLIA_RPC_URL": "rpc", "DEPLOYER_PK": _pk(1), "AEQUITAS_DEVTOOLS": "1"},
        registry=_registry(), wallets=_wallets(), dry_run=False,
    )
    step = next(s for s in sbx.empty_steps() if s.key == "post_contributions")
    sbx.run_step(step, ctx)
    # All members inactive → all skipped → skipped_existing
    assert step.status == "skipped_existing", f"expected skipped_existing, got {step.status!r}"


def test_unknown_contribution_error_still_fails(monkeypatch):
    """An unrecognised revert on contribute must remain fatal."""
    import engine.sandbox_sepolia as sbx

    class _Fail:
        returncode = 1
        stdout = ""
        stderr = "execution reverted: SomeUnknownError()"

    monkeypatch.setattr(sbx.subprocess, "run", lambda *a, **kw: _Fail())
    monkeypatch.setattr(sbx.shutil, "which", lambda x: "/usr/bin/cast")

    ctx = RunContext(
        env={"SEPOLIA_RPC_URL": "rpc", "DEPLOYER_PK": _pk(1), "AEQUITAS_DEVTOOLS": "1"},
        registry=_registry(), wallets=_wallets(), dry_run=False,
    )
    step = next(s for s in sbx.empty_steps() if s.key == "post_contributions")
    sbx.run_step(step, ctx)
    assert step.status == "failed", f"expected failed, got {step.status!r}"


def test_full_demo_continues_after_one_contribution_skipped(monkeypatch):
    """If some contribute calls hit InactiveMember and others succeed, the step is
    not fatal — the full demo continues through the remaining steps."""
    import engine.sandbox_sepolia as sbx

    tx = "0x" + ("cc" * 32)
    call_count: list[int] = [0]

    def _run(*a, **kw):
        call_count[0] += 1
        # First call (for the near_retiree wallet) hits InactiveMember.
        if call_count[0] == 1:
            class _Fail:
                returncode = 1; stdout = ""; stderr = "InactiveMember(0xA0A0A0A0A0A0A0A0A0A0A0A0A0A0A0A0A0A0A0A0)"
            return _Fail()
        # All subsequent calls succeed.
        class _Ok:
            returncode = 0
            stdout = f'{{"transactionHash":"{tx}","status":"0x1","gasUsed":"0x5208"}}'
            stderr = ""
        return _Ok()

    monkeypatch.setattr(sbx.subprocess, "run", _run)
    monkeypatch.setattr(sbx.shutil, "which", lambda x: "/usr/bin/cast")
    monkeypatch.setattr(sbx, "_cast_call", lambda *a, **kw: None)

    ctx = RunContext(
        env={"SEPOLIA_RPC_URL": "rpc", "DEPLOYER_PK": _pk(1), "AEQUITAS_DEVTOOLS": "1"},
        registry=_registry(), wallets=_wallets(), dry_run=False,
    )
    step = next(s for s in sbx.empty_steps() if s.key == "post_contributions")
    sbx.run_step(step, ctx)
    # At least some succeeded → confirmed (not failed)
    assert step.status == "confirmed", f"expected confirmed, got {step.status!r}"


def test_open_retirement_stream_already_exists_treated_as_skipped_existing(monkeypatch):
    """StreamAlreadyExists from BenefitStreamer.startStream — openRetirement is
    idempotent on repeated runs."""
    import engine.sandbox_sepolia as sbx

    class _Fail:
        returncode = 1
        stdout = ""
        stderr = "execution reverted: StreamAlreadyExists(0xA0A0A0A0A0A0A0A0A0A0A0A0A0A0A0A0A0A0A0A0)"

    monkeypatch.setattr(sbx.subprocess, "run", lambda *a, **kw: _Fail())
    monkeypatch.setattr(sbx.shutil, "which", lambda x: "/usr/bin/cast")

    ctx = RunContext(
        env={"SEPOLIA_RPC_URL": "rpc", "DEPLOYER_PK": _pk(1), "AEQUITAS_DEVTOOLS": "1"},
        registry=_registry(), wallets=_wallets(), dry_run=False,
    )
    step = next(s for s in sbx.empty_steps() if s.key == "open_retirement")
    sbx.run_step(step, ctx)
    assert step.status == "skipped_existing", f"expected skipped_existing, got {step.status!r}"


# ---- Phase 4b: raw hex selector matching (live-RPC revert data) -------------

def test_inactive_member_raw_selector_is_idempotent():
    """0xf7476063 alone in the error string must be recognised as idempotent —
    live RPC nodes return only ABI-encoded revert data, not a decoded name."""
    from engine.sandbox_sepolia import _is_idempotent_revert
    raw = (
        'Failed to estimate gas, execution reverted, '
        'data: "0xf74760630000000000000000000000004ed2d4e6b1794a5846e8fa7efdc2948e0e7bf2c8"'
    )
    assert _is_idempotent_revert(raw), "raw InactiveMember selector should be idempotent"


def test_stream_already_exists_raw_selector_is_idempotent():
    """0xc6fd1730 alone in the error string must be recognised as idempotent."""
    from engine.sandbox_sepolia import _is_idempotent_revert
    raw = (
        'execution reverted, '
        'data: "0xc6fd17300000000000000000000000004ed2d4e6b1794a5846e8fa7efdc2948e0e7bf2c8"'
    )
    assert _is_idempotent_revert(raw), "raw StreamAlreadyExists selector should be idempotent"


def test_unknown_raw_selector_is_not_idempotent():
    """An unrecognised 4-byte selector must NOT be treated as idempotent."""
    from engine.sandbox_sepolia import _is_idempotent_revert
    raw = (
        'execution reverted, '
        'data: "0xdeadbeef0000000000000000000000004ed2d4e6b1794a5846e8fa7efdc2948e0e7bf2c8"'
    )
    assert not _is_idempotent_revert(raw), "unknown selector should not be idempotent"


def test_contribution_step_skips_raw_inactive_member_selector(monkeypatch):
    """When cast returns only 0xf7476063 (no decoded name), the contribution
    step treats that member as skipped_existing and continues for the others."""
    import engine.sandbox_sepolia as sbx

    raw_error = (
        "Failed to estimate gas, execution reverted, "
        'data: "0xf74760630000000000000000000000004ed2d4e6b1794a5846e8fa7efdc2948e0e7bf2c8"'
    )
    tx = "0x" + ("ee" * 32)
    call_count: list[int] = [0]

    def _run(*a, **kw):
        call_count[0] += 1
        if call_count[0] == 1:
            class _Fail:
                returncode = 1; stdout = ""; stderr = raw_error
            return _Fail()
        class _Ok:
            returncode = 0
            stdout = f'{{"transactionHash":"{tx}","status":"0x1","gasUsed":"0x5208"}}'
            stderr = ""
        return _Ok()

    monkeypatch.setattr(sbx.subprocess, "run", _run)
    monkeypatch.setattr(sbx.shutil, "which", lambda x: "/usr/bin/cast")
    monkeypatch.setattr(sbx, "_cast_call", lambda *a, **kw: None)

    ctx = RunContext(
        env={"SEPOLIA_RPC_URL": "rpc", "DEPLOYER_PK": _pk(1), "AEQUITAS_DEVTOOLS": "1"},
        registry=_registry(), wallets=_wallets(), dry_run=False,
    )
    step = next(s for s in sbx.empty_steps() if s.key == "post_contributions")
    sbx.run_step(step, ctx)
    # First member skipped, remaining 5 confirmed → confirmed overall
    assert step.status == "confirmed", f"expected confirmed, got {step.status!r}"
