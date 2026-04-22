"""Tests for engine.events — the SimEvent timeline type."""
from __future__ import annotations

import pathlib
import re

from engine.events import (
    BACKSTOP_DEPOSIT,
    BACKSTOP_RELEASE,
    CONTRACT_MAP,
    CONTRIBUTION,
    DEATH,
    INFLATION_SHOCK,
    INVESTMENT_RETURN,
    JOIN,
    MARKET_CRASH,
    MORTALITY_SPIKE,
    PROPOSAL,
    RETIREMENT,
    SEVERITY_MAP,
    STRESS_RUN,
    SimEvent,
    YEAR_CLOSED,
    summarise_events,
)


ALL_KINDS = [
    JOIN, CONTRIBUTION, RETIREMENT, DEATH, INVESTMENT_RETURN,
    MARKET_CRASH, MORTALITY_SPIKE, INFLATION_SHOCK, PROPOSAL,
    STRESS_RUN, BACKSTOP_DEPOSIT, BACKSTOP_RELEASE, YEAR_CLOSED,
]


def test_every_kind_has_contract_and_severity():
    for k in ALL_KINDS:
        assert k in CONTRACT_MAP, f"missing contract for {k}"
        assert k in SEVERITY_MAP, f"missing severity for {k}"
        assert SEVERITY_MAP[k] in ("muted", "good", "warn", "bad")


def test_simevent_properties():
    e = SimEvent(2030, MARKET_CRASH, {"drop": 0.25})
    assert e.contract == CONTRACT_MAP[MARKET_CRASH]
    assert e.severity == "bad"
    assert "MARKET CRASH" in e.message()
    assert "25%" in e.message()


def test_message_for_each_kind_is_a_nonempty_string():
    data_fixtures = {
        JOIN:              {"count": 3},
        CONTRIBUTION:      {"total": 100_000.0},
        RETIREMENT:        {"count": 2},
        DEATH:             {"count": 1},
        INVESTMENT_RETURN: {"return": 0.055},
        MARKET_CRASH:      {"drop": 0.20},
        MORTALITY_SPIKE:   {"multiplier": 1.5},
        INFLATION_SHOCK:   {"inflation": 0.08},
        PROPOSAL:          {"name": "X", "passes": True},
        STRESS_RUN:        {"pass_rate": 0.9},
        BACKSTOP_DEPOSIT:  {"amount": 5_000},
        BACKSTOP_RELEASE:  {"amount": 3_000},
        YEAR_CLOSED:       {"funded_ratio": 1.02},
    }
    for kind in ALL_KINDS:
        e = SimEvent(2029, kind, data_fixtures.get(kind, {}))
        msg = e.message()
        assert isinstance(msg, str) and msg.strip()
        assert str(2029) in msg


def test_to_dict_roundtrip_shape():
    e = SimEvent(2030, JOIN, {"count": 7})
    d = e.to_dict()
    assert d["year"] == 2030
    assert d["kind"] == JOIN
    assert d["severity"] == "muted"
    assert d["contract"] == CONTRACT_MAP[JOIN]
    assert "message" in d
    assert d["data_count"] == 7


def test_summarise_events_counts_by_kind():
    events = [
        SimEvent(2030, JOIN, {"count": 1}),
        SimEvent(2030, JOIN, {"count": 2}),
        SimEvent(2031, DEATH, {"count": 1}),
    ]
    out = summarise_events(events)
    assert out[JOIN] == 2
    assert out[DEATH] == 1


def test_proposal_pass_and_fail_formatting():
    p_pass = SimEvent(2030, PROPOSAL, {"name": "Trim", "passes": True})
    p_fail = SimEvent(2030, PROPOSAL, {"name": "Trim", "passes": False})
    assert "PASSED" in p_pass.message()
    assert "FAILED" in p_fail.message()


def test_contract_map_names_real_solidity_functions():
    """Every non-placeholder contract pill must refer to an actual
    function in contracts/src/*.sol.

    This guards the hybrid story: if a Solidity contract is renamed,
    the Python twin's event timeline will break this test before it
    ships a stale pill to the UI.
    """
    repo_root = pathlib.Path(__file__).resolve().parents[1]
    src_dir = repo_root / "contracts" / "src"
    if not src_dir.is_dir():
        return  # contracts not vendored in this checkout — skip silently

    blob = "\n".join(
        p.read_text() for p in sorted(src_dir.glob("*.sol"))
    )
    for kind, ref in CONTRACT_MAP.items():
        if ref == "—":
            continue
        contract, _, func = ref.partition(".")
        assert contract, f"empty contract in mapping for {kind}"
        assert func, f"empty function in mapping for {kind}"
        # contracts/src/<Contract>.sol must exist
        assert (src_dir / f"{contract}.sol").is_file(), (
            f"CONTRACT_MAP[{kind}] points at {contract}.sol which "
            f"does not exist under contracts/src/"
        )
        # function must appear as `function <name>(` somewhere in src
        pattern = re.compile(rf"function\s+{re.escape(func)}\s*\(")
        assert pattern.search(blob), (
            f"CONTRACT_MAP[{kind}] = {ref!r} but no matching "
            f"`function {func}(` found in contracts/src/"
        )
