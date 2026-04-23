"""Tests for the Python↔chain bridge.

Focus on the *encoding contract* between Python and Solidity:
fixed-point scale, cohort bucketing, bytes32 padding, argument order.
"""
from __future__ import annotations

import pytest

from engine import chain_bridge as cb
from engine.experience_oracle import deterministic_sandbox_snapshot
from engine.ledger import CohortLedger
from engine.models import Proposal


# ----------------------------------------------------------------- primitives

def test_to_fixed_and_back_roundtrip():
    assert cb.to_fixed(1.0) == 10 ** 18
    assert cb.to_fixed(0.5) == 5 * 10 ** 17
    assert cb.to_fixed(0) == 0
    assert abs(cb.from_fixed(cb.to_fixed(1.25)) - 1.25) < 1e-12


def test_cohort_of_matches_solidity_rule():
    assert cb.cohort_of(1960) == 1960
    assert cb.cohort_of(1963) == 1960
    assert cb.cohort_of(1995) == 1995
    assert cb.cohort_of(1999) == 1995


def test_normalize_address_rejects_bogus():
    with pytest.raises(ValueError):
        cb.normalize_address("0xnothex")        # not hex
    with pytest.raises(ValueError):
        cb.normalize_address("no-0x-prefix")    # missing prefix
    # short demo ids are accepted (zero-padded) for the Streamlit demo
    assert cb.normalize_address("0xA001") == "0x" + "0" * 36 + "a001"
    good = "0x" + "ab" * 20
    assert cb.normalize_address(good.upper()) == good.lower()


def test_string_to_bytes32_pads_right():
    encoded = cb.string_to_bytes32("p95_gini")
    assert encoded.startswith("0x")
    assert len(encoded) == 2 + 64
    # ASCII "p95_gini" = 70 39 35 5f 67 69 6e 69
    assert encoded[:18] == "0x7039355f67696e69"
    assert encoded.endswith("00" * (31 - 8))


def test_string_to_bytes32_rejects_too_long():
    with pytest.raises(ValueError):
        cb.string_to_bytes32("x" * 32)


def test_hash_bytes32_is_deterministic():
    a = cb.hash_bytes32("hello")
    b = cb.hash_bytes32(b"hello")
    assert a == b
    assert a.startswith("0x") and len(a) == 2 + 64


# ----------------------------------------------------------------- encoders

def _tiny_ledger() -> CohortLedger:
    led = CohortLedger(piu_price=1.0, valuation_year=2026)
    led.register_member("0x" + "a" * 40, 1960)
    led.register_member("0x" + "b" * 40, 1990)
    led.contribute("0x" + "a" * 40, 100.0)
    led.contribute("0x" + "b" * 40, 50.0)
    return led


def test_encode_register_and_contribution_shapes():
    led = _tiny_ledger()
    m = led.get_all_members()[0]
    c = cb.encode_register(m)
    assert c.contract == "CohortLedger"
    assert c.function == "registerMember"
    assert c.args == [m.wallet.lower(), 1960]

    c2 = cb.encode_contribution(m.wallet, 100.0, amount_unit="ether")
    assert c2.function == "contribute"
    assert c2.args[1] == 100 * 10 ** 18


def test_encode_contribution_rejects_bad_unit():
    with pytest.raises(ValueError):
        cb.encode_contribution("0x" + "a" * 40, 1, amount_unit="banana")


def test_encode_baseline_sorts_and_scales():
    led = _tiny_ledger()
    cv = led.cohort_valuation()
    call = cb.encode_baseline(cv)
    assert call.contract == "FairnessGate"
    assert call.function == "setBaseline"
    cohorts, epvs = call.args
    assert cohorts == sorted(cohorts)
    assert len(cohorts) == len(epvs)
    # EPVs should be int and 1e18-scaled — they should be large ints
    assert all(isinstance(e, int) for e in epvs)


def test_encode_proposal_applies_multipliers():
    led = _tiny_ledger()
    cv = led.cohort_valuation()
    # cut the youngest cohort's benefits by 50% — the encoded EPV must drop
    youngest = max(cv.keys())
    baseline_call = cb.encode_baseline(cv)
    baseline_epv = dict(zip(baseline_call.args[0], baseline_call.args[1]))[youngest]

    p = Proposal(name="cut youngest", description="", multipliers={youngest: 0.5})
    prop_call = cb.encode_proposal(p, cv, delta=0.05)
    assert prop_call.function == "submitAndEvaluate"
    cohorts, new_epvs = prop_call.args[1], prop_call.args[2]
    new_youngest = dict(zip(cohorts, new_epvs))[youngest]
    assert abs(new_youngest - baseline_epv * 0.5) < 2  # rounding tolerance


def test_encode_stress_update_range_and_types():
    call = cb.encode_stress_update(0.82, "p95_gini>threshold", b"demo")
    assert call.contract == "StressOracle"
    level, reason, data_hash = call.args
    assert level == cb.to_fixed(0.82)
    assert reason.startswith("0x") and len(reason) == 2 + 64
    assert data_hash.startswith("0x") and len(data_hash) == 2 + 64


def test_encode_stress_update_rejects_out_of_range():
    with pytest.raises(ValueError):
        cb.encode_stress_update(1.5, "bad")
    with pytest.raises(ValueError):
        cb.encode_stress_update(-0.1, "bad")


def test_encode_piu_price_update_shape():
    call = cb.encode_piu_price_update(1.125, cpi_level=112.5)
    assert call.contract == "CohortLedger"
    assert call.function == "setPiuPrice"
    assert call.args == [cb.to_fixed(1.125)]
    assert "CPI 112.500" in call.note


def test_encode_mortality_basis_publish_shape():
    led = _tiny_ledger()
    snapshot = deterministic_sandbox_snapshot(
        members=led.get_all_members(),
        valuation_year=led.valuation_year,
    )
    call = cb.encode_mortality_basis_publish(snapshot)
    assert call.contract == "MortalityBasisOracle"
    assert call.function == "publishBasis"
    assert call.args[0] == 1
    assert call.args[3] == int(round(snapshot.credibility_weight * 10_000))
    assert call.args[5].startswith("0x")


def test_ledger_to_chain_calls_orders_register_before_contribute():
    led = _tiny_ledger()
    calls = cb.ledger_to_chain_calls(led)
    # for each wallet, registerMember must precede contribute
    seen = {}
    for c in calls:
        wallet = c.args[0]
        if c.function == "registerMember":
            seen[wallet] = "r"
        elif c.function == "contribute":
            assert seen.get(wallet) == "r", f"{wallet}: contribute before register"


def test_ledger_to_chain_calls_includes_piu_update_when_price_moved():
    led = CohortLedger(piu_price=1.0, current_cpi=110.0, valuation_year=2026)
    led.register_member("0x" + "a" * 40, 1985)
    calls = cb.ledger_to_chain_calls(led)
    assert calls[0].function == "setPiuPrice"
    assert calls[0].contract == "CohortLedger"


def test_proposal_to_chain_calls_returns_baseline_then_proposal():
    led = _tiny_ledger()
    p = Proposal(name="demo", description="", multipliers={1995: 1.01})
    calls = cb.proposal_to_chain_calls(led, p, delta=0.05)
    assert len(calls) == 2
    assert calls[0].function == "setBaseline"
    assert calls[1].function == "submitAndEvaluate"


def test_encode_pool_deposit_sets_value_and_args():
    call = cb.encode_pool_deposit("0xA001", 2.5)
    assert call.contract == "LongevaPool"
    assert call.function == "deposit"
    assert call.args[0] == "0x" + "0" * 36 + "a001"
    assert call.args[1] == cb.to_fixed(2.5)
    assert call.value_wei == cb.to_fixed(2.5)


def test_encode_open_retirement_shape():
    call = cb.encode_open_retirement("0xA001", 10.0, 1.2, start_timestamp=0)
    assert call.contract == "VestaRouter"
    assert call.function == "openRetirement"
    assert call.args[1] == cb.to_fixed(10.0)
    assert call.args[2] == cb.to_fixed(1.2)
    assert call.args[3] == 0


def test_encode_backstop_deposit_carries_value():
    call = cb.encode_backstop_deposit(3.0)
    assert call.contract == "BackstopVault"
    assert call.function == "deposit"
    assert call.args == []
    assert call.value_wei == cb.to_fixed(3.0)


def test_encode_backstop_release_rejects_nonpositive():
    import pytest as _pytest
    with _pytest.raises(ValueError):
        cb.encode_backstop_release(0)
    with _pytest.raises(ValueError):
        cb.encode_backstop_release(-1)


def test_encode_backstop_release_shape():
    call = cb.encode_backstop_release(0.5)
    assert call.contract == "BackstopVault"
    assert call.function == "release"
    assert call.args == [cb.to_fixed(0.5)]
    assert call.value_wei == 0


def test_calls_to_json_is_serialisable():
    import json
    led = _tiny_ledger()
    calls = cb.ledger_to_chain_calls(led)
    blob = json.dumps(cb.calls_to_json(calls))  # must not raise
    assert "CohortLedger" in blob
