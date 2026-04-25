"""Tests for the actuarial proof-layer serializers."""
from __future__ import annotations

from engine.actuarial_proof import (
    build_default_proof_bundle,
    build_parameter_snapshot,
    build_valuation_snapshot,
    default_method_versions,
    method_key,
)
from engine.ledger import CohortLedger


def _proof_ledger() -> CohortLedger:
    led = CohortLedger(piu_price=1.08, current_cpi=108.0, valuation_year=2026)
    led.register_member("0x" + "a" * 40, 1960)
    led.register_member("0x" + "b" * 40, 1980)
    led.register_member("0x" + "c" * 40, 1990)
    led.contribute("0x" + "a" * 40, 120.0)
    led.contribute("0x" + "b" * 40, 80.0)
    led.contribute("0x" + "c" * 40, 55.0)
    return led


def test_method_key_is_deterministic():
    assert method_key("EPV", "epv_discrete_v1") == method_key("EPV", "epv_discrete_v1")
    assert method_key("EPV", "epv_discrete_v1") != method_key("EPV", "epv_discrete_v2")


def test_default_method_versions_cover_core_families():
    methods = default_method_versions(effective_date=2026)
    families = {row.method_family for row in methods}
    assert families == {"MORTALITY_BASIS", "EPV", "MWR", "FAIRNESS_CORRIDOR"}
    assert all(row.method_key.startswith("0x") for row in methods)


def test_parameter_and_valuation_snapshot_hashes_are_stable():
    led = _proof_ledger()
    params_a = build_parameter_snapshot(led, valuation_date=2026, fairness_delta=0.05, mortality_basis_version=1)
    params_b = build_parameter_snapshot(led, valuation_date=2026, fairness_delta=0.05, mortality_basis_version=1)
    assert params_a.parameter_set_key == params_b.parameter_set_key

    snapshot_a = build_valuation_snapshot(led, params_a)
    snapshot_b = build_valuation_snapshot(led, params_b)
    assert snapshot_a.input_hash == snapshot_b.input_hash
    assert snapshot_a.member_snapshot_hash == snapshot_b.member_snapshot_hash


def test_default_proof_bundle_links_methods_parameters_and_results():
    bundle = build_default_proof_bundle(
        _proof_ledger(),
        valuation_date=2026,
        fairness_delta=0.05,
        mortality_basis_version=1,
    )
    assert bundle["methods"]
    assert bundle["parameter_snapshot"].parameter_set_key == bundle["valuation_snapshot"].parameter_set_key
    assert bundle["result_bundle"].scheme_summary_key == bundle["scheme_summary"].scheme_summary_key
    assert bundle["result_bundle"].valuation_snapshot_key == bundle["valuation_snapshot"].valuation_snapshot_key
    assert bundle["spot_check"].tolerance_bps == 25
