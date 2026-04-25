"""Actuarial proof-layer serializers and commitment helpers.

Aequitas keeps the full actuarial engine off-chain in Python. This module
builds the compact, publishable proof objects that are suitable for the
on-chain audit layer:

* methodology versions,
* parameter snapshots,
* valuation-input commitments,
* scheme/cohort summary commitments,
* result-bundle provenance,
* bounded spot-check payloads.

The chain does not re-run the full pension engine. It records which
method/version/parameter/input set governed a published result and gives
auditors enough deterministic material to run selected spot checks.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any, Mapping

from engine.ledger import CohortLedger


def _stable_json(payload: Any) -> str:
    """Return a canonical JSON encoding for hashing and proof bundles."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def _sha256_hex(payload: Any) -> str:
    """Import locally so this module stays stdlib-only."""
    from hashlib import sha256

    if not isinstance(payload, (bytes, bytearray)):
        payload = _stable_json(payload).encode("utf-8")
    return "0x" + sha256(payload).hexdigest()


def method_key(method_family: str, version: str) -> str:
    """Deterministic method key published both off-chain and on-chain."""
    return _sha256_hex({"family": str(method_family), "version": str(version)})


def bundle_hash(payload: Mapping[str, Any]) -> str:
    """Deterministic commitment hash for an actuarial proof bundle."""
    return _sha256_hex(dict(payload))


def _to_bps(x: float) -> int:
    return int(round(float(x) * 10_000))


def _to_scaled(x: float, *, scale: int = 10_000) -> int:
    return int(round(float(x) * scale))


@dataclass(frozen=True)
class ActuarialMethodVersion:
    method_key: str
    method_family: str
    version: str
    spec_hash: str
    reference_impl_hash: str
    parameter_schema_hash: str
    effective_date: int
    metadata_hash: str

    def as_payload(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ActuarialParameterSnapshot:
    parameter_set_key: str
    valuation_date: int
    discount_rate_bps: int
    salary_growth_bps: int
    investment_return_bps: int
    piu_price_fixed: int
    fairness_delta_bps: int
    mortality_basis_version: int
    parameter_hash: str

    def as_payload(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ActuarialValuationSnapshot:
    valuation_snapshot_key: str
    parameter_set_key: str
    member_snapshot_hash: str
    cohort_summary_hash: str
    member_count: int
    cohort_count: int
    input_hash: str

    def as_payload(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ActuarialSchemeSummary:
    scheme_summary_key: str
    valuation_snapshot_key: str
    epv_contributions_fixed: int
    epv_benefits_fixed: int
    funded_ratio_bps: int
    mwr_bps: int
    summary_hash: str

    def as_payload(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ActuarialCohortSummary:
    cohort_summary_key: str
    valuation_snapshot_key: str
    cohort: int
    epv_contributions_fixed: int
    epv_benefits_fixed: int
    mwr_bps: int
    members: int
    summary_hash: str

    def as_payload(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ActuarialResultBundle:
    result_bundle_key: str
    parameter_set_key: str
    valuation_snapshot_key: str
    mortality_method_key: str
    epv_method_key: str
    mwr_method_key: str
    fairness_method_key: str
    scheme_summary_key: str
    cohort_digest: str
    result_hash: str

    def as_payload(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ActuarialSpotCheck:
    expected_mwr_fixed: int
    tolerance_bps: int
    epv_benefits_fixed: int
    epv_contributions_fixed: int

    def as_payload(self) -> dict[str, Any]:
        return asdict(self)


def default_method_versions(*, effective_date: int) -> list[ActuarialMethodVersion]:
    """Version catalogue for the MVP proof layer."""
    methods = [
        (
            "MORTALITY_BASIS",
            "gompertz_makeham_blended_v1",
            "Hybrid mortality basis: Gompertz prior blended toward cohort experience by credibility weight.",
            "engine/experience_oracle.py",
            "schema:mortality-basis/v1",
            "metadata:private experience study off-chain, compact basis snapshot on-chain",
        ),
        (
            "EPV",
            "epv_discrete_v1",
            "Discrete annual EPV with explicit discount and survival terms.",
            "engine/actuarial.py",
            "schema:epv-parameters/v1",
            "metadata:member loop remains off-chain; chain only spot-checks bounded vectors",
        ),
        (
            "MWR",
            "mwr_ratio_v1",
            "Money-worth ratio defined as EPV benefits divided by EPV contributions.",
            "engine/fairness.py",
            "schema:mwr-summary/v1",
            "metadata:scheme and cohort summaries are committed on-chain",
        ),
        (
            "FAIRNESS_CORRIDOR",
            "fairness_corridor_v1",
            "Pairwise EPV-change corridor against a declared benchmark and delta.",
            "engine/fairness.py",
            "schema:corridor/v1",
            "metadata:chain verifies bounded corridor checks, not full proposal simulation",
        ),
    ]
    out: list[ActuarialMethodVersion] = []
    for family, version, spec, ref_impl, schema, meta in methods:
        out.append(
            ActuarialMethodVersion(
                method_key=method_key(family, version),
                method_family=family,
                version=version,
                spec_hash=_sha256_hex(spec),
                reference_impl_hash=_sha256_hex(ref_impl),
                parameter_schema_hash=_sha256_hex(schema),
                effective_date=int(effective_date),
                metadata_hash=_sha256_hex(meta),
            )
        )
    return out


def build_parameter_snapshot(
    ledger: CohortLedger,
    *,
    valuation_date: int,
    fairness_delta: float,
    mortality_basis_version: int,
) -> ActuarialParameterSnapshot:
    payload = {
        "valuation_date": int(valuation_date),
        "discount_rate": float(ledger.discount_rate),
        "salary_growth": float(ledger.salary_growth),
        "investment_return": float(ledger.investment_return),
        "piu_price": float(ledger.piu_price),
        "fairness_delta": float(fairness_delta),
        "mortality_basis_version": int(mortality_basis_version),
    }
    parameter_hash = bundle_hash(payload)
    return ActuarialParameterSnapshot(
        parameter_set_key=parameter_hash,
        valuation_date=int(valuation_date),
        discount_rate_bps=_to_bps(ledger.discount_rate),
        salary_growth_bps=_to_bps(ledger.salary_growth),
        investment_return_bps=_to_bps(ledger.investment_return),
        piu_price_fixed=_to_scaled(ledger.piu_price, scale=10**18),
        fairness_delta_bps=_to_bps(fairness_delta),
        mortality_basis_version=int(mortality_basis_version),
        parameter_hash=parameter_hash,
    )


def build_valuation_snapshot(
    ledger: CohortLedger,
    parameter_snapshot: ActuarialParameterSnapshot,
) -> ActuarialValuationSnapshot:
    member_rows = [
        {
            "wallet": m.wallet.lower(),
            "birth_year": int(m.birth_year),
            "retirement_age": int(m.retirement_age),
            "sex": str(m.sex),
            "salary": round(float(m.salary), 8),
            "contribution_rate": round(float(m.contribution_rate), 8),
            "total_contributions": round(float(m.total_contributions), 8),
            "piu_balance": round(float(m.piu_balance), 8),
            "retired": not bool(getattr(m, "active", True)),
        }
        for m in sorted(ledger.get_all_members(), key=lambda member: str(member.wallet).lower())
    ]
    cohort_rows = [
        {
            "cohort": int(cohort),
            "members": int(row["members"]),
            "epv_contributions": round(float(row["epv_contributions"]), 8),
            "epv_benefits": round(float(row["epv_benefits"]), 8),
            "money_worth_ratio": round(float(row["money_worth_ratio"]), 8),
        }
        for cohort, row in sorted(ledger.cohort_valuation().items())
    ]
    member_snapshot_hash = bundle_hash({"members": member_rows})
    cohort_summary_hash = bundle_hash({"cohorts": cohort_rows})
    input_hash = bundle_hash(
        {
            "parameter_set_key": parameter_snapshot.parameter_set_key,
            "member_snapshot_hash": member_snapshot_hash,
            "cohort_summary_hash": cohort_summary_hash,
        }
    )
    return ActuarialValuationSnapshot(
        valuation_snapshot_key=input_hash,
        parameter_set_key=parameter_snapshot.parameter_set_key,
        member_snapshot_hash=member_snapshot_hash,
        cohort_summary_hash=cohort_summary_hash,
        member_count=len(member_rows),
        cohort_count=len(cohort_rows),
        input_hash=input_hash,
    )


def build_scheme_summary(
    ledger: CohortLedger,
    valuation_snapshot: ActuarialValuationSnapshot,
) -> ActuarialSchemeSummary:
    valuations = ledger.value_all()
    epv_contributions = float(sum(v.epv_contributions for v in valuations))
    epv_benefits = float(sum(v.epv_benefits for v in valuations))
    mwr = (epv_benefits / epv_contributions) if epv_contributions else 0.0
    contributions_paid = float(sum(m.total_contributions for m in ledger.get_all_members()))
    funded_ratio = (contributions_paid / epv_benefits) if epv_benefits else 0.0
    summary_payload = {
        "valuation_snapshot_key": valuation_snapshot.valuation_snapshot_key,
        "epv_contributions": round(epv_contributions, 8),
        "epv_benefits": round(epv_benefits, 8),
        "funded_ratio": round(funded_ratio, 8),
        "mwr": round(mwr, 8),
    }
    summary_hash = bundle_hash(summary_payload)
    return ActuarialSchemeSummary(
        scheme_summary_key=summary_hash,
        valuation_snapshot_key=valuation_snapshot.valuation_snapshot_key,
        epv_contributions_fixed=_to_scaled(epv_contributions, scale=10**18),
        epv_benefits_fixed=_to_scaled(epv_benefits, scale=10**18),
        funded_ratio_bps=_to_bps(funded_ratio),
        mwr_bps=_to_bps(mwr),
        summary_hash=summary_hash,
    )


def build_cohort_summaries(
    ledger: CohortLedger,
    valuation_snapshot: ActuarialValuationSnapshot,
) -> list[ActuarialCohortSummary]:
    rows: list[ActuarialCohortSummary] = []
    for cohort, row in sorted(ledger.cohort_valuation().items()):
        payload = {
            "valuation_snapshot_key": valuation_snapshot.valuation_snapshot_key,
            "cohort": int(cohort),
            "epv_contributions": round(float(row["epv_contributions"]), 8),
            "epv_benefits": round(float(row["epv_benefits"]), 8),
            "mwr": round(float(row["money_worth_ratio"]), 8),
            "members": int(row["members"]),
        }
        summary_hash = bundle_hash(payload)
        rows.append(
            ActuarialCohortSummary(
                cohort_summary_key=summary_hash,
                valuation_snapshot_key=valuation_snapshot.valuation_snapshot_key,
                cohort=int(cohort),
                epv_contributions_fixed=_to_scaled(float(row["epv_contributions"]), scale=10**18),
                epv_benefits_fixed=_to_scaled(float(row["epv_benefits"]), scale=10**18),
                mwr_bps=_to_bps(float(row["money_worth_ratio"])),
                members=int(row["members"]),
                summary_hash=summary_hash,
            )
        )
    return rows


def build_result_bundle(
    *,
    parameter_snapshot: ActuarialParameterSnapshot,
    valuation_snapshot: ActuarialValuationSnapshot,
    scheme_summary: ActuarialSchemeSummary,
    cohort_summaries: list[ActuarialCohortSummary],
    mortality_method_key: str,
    epv_method_key: str,
    mwr_method_key: str,
    fairness_method_key: str,
) -> ActuarialResultBundle:
    cohort_digest = bundle_hash({"cohort_summary_keys": [row.cohort_summary_key for row in cohort_summaries]})
    payload = {
        "parameter_set_key": parameter_snapshot.parameter_set_key,
        "valuation_snapshot_key": valuation_snapshot.valuation_snapshot_key,
        "scheme_summary_key": scheme_summary.scheme_summary_key,
        "cohort_digest": cohort_digest,
        "mortality_method_key": mortality_method_key,
        "epv_method_key": epv_method_key,
        "mwr_method_key": mwr_method_key,
        "fairness_method_key": fairness_method_key,
    }
    result_hash = bundle_hash(payload)
    return ActuarialResultBundle(
        result_bundle_key=result_hash,
        parameter_set_key=parameter_snapshot.parameter_set_key,
        valuation_snapshot_key=valuation_snapshot.valuation_snapshot_key,
        mortality_method_key=mortality_method_key,
        epv_method_key=epv_method_key,
        mwr_method_key=mwr_method_key,
        fairness_method_key=fairness_method_key,
        scheme_summary_key=scheme_summary.scheme_summary_key,
        cohort_digest=cohort_digest,
        result_hash=result_hash,
    )


def build_default_proof_bundle(
    ledger: CohortLedger,
    *,
    valuation_date: int,
    fairness_delta: float,
    mortality_basis_version: int,
) -> dict[str, Any]:
    """Build a full deterministic proof bundle from the current ledger state."""
    methods = default_method_versions(effective_date=valuation_date)
    methods_by_family = {m.method_family: m for m in methods}
    parameter_snapshot = build_parameter_snapshot(
        ledger,
        valuation_date=valuation_date,
        fairness_delta=fairness_delta,
        mortality_basis_version=mortality_basis_version,
    )
    valuation_snapshot = build_valuation_snapshot(ledger, parameter_snapshot)
    scheme_summary = build_scheme_summary(ledger, valuation_snapshot)
    cohort_summaries = build_cohort_summaries(ledger, valuation_snapshot)
    result_bundle = build_result_bundle(
        parameter_snapshot=parameter_snapshot,
        valuation_snapshot=valuation_snapshot,
        scheme_summary=scheme_summary,
        cohort_summaries=cohort_summaries,
        mortality_method_key=methods_by_family["MORTALITY_BASIS"].method_key,
        epv_method_key=methods_by_family["EPV"].method_key,
        mwr_method_key=methods_by_family["MWR"].method_key,
        fairness_method_key=methods_by_family["FAIRNESS_CORRIDOR"].method_key,
    )
    spot_check = ActuarialSpotCheck(
        expected_mwr_fixed=_to_scaled(float(scheme_summary.mwr_bps) / 10_000, scale=10**18),
        tolerance_bps=25,
        epv_benefits_fixed=scheme_summary.epv_benefits_fixed,
        epv_contributions_fixed=scheme_summary.epv_contributions_fixed,
    )
    return {
        "methods": methods,
        "parameter_snapshot": parameter_snapshot,
        "valuation_snapshot": valuation_snapshot,
        "scheme_summary": scheme_summary,
        "cohort_summaries": cohort_summaries,
        "result_bundle": result_bundle,
        "spot_check": spot_check,
    }
