"""Tests for mortality learning and publishable basis snapshots."""
from __future__ import annotations

from engine.experience_oracle import (
    CredibilityConfig,
    ExperienceOracle,
    blend_multiplier,
    credibility_weight,
    deterministic_sandbox_snapshot,
)
from engine.models import Member


def test_credibility_weight_stays_low_below_thresholds():
    cfg = CredibilityConfig(
        min_exposure_years=1000,
        min_deaths=10,
        full_exposure_years=4000,
        full_deaths=40,
        advisory_cap=0.25,
    )
    weight = credibility_weight(exposure_years=500, observed_deaths=3, config=cfg)
    assert 0.0 <= weight <= 0.25


def test_blend_multiplier_moves_smoothly_from_prior():
    cfg = CredibilityConfig(max_multiplier_step=0.10)
    blended = blend_multiplier(
        prior_multiplier=1.00,
        experience_multiplier=1.40,
        weight=1.0,
        config=cfg,
    )
    assert blended == 1.10


def test_experience_oracle_builds_publishable_snapshot():
    oracle = ExperienceOracle()
    oracle.record_period(
        cohorts=[1960, 1960, 1980, 1980],
        ages=[66, 67, 45, 46],
        sexes=["M", "F", "M", "F"],
        retired=[True, True, False, False],
        death_flags=[False, True, False, False],
        exposure_years=1.0,
    )
    snapshot = oracle.build_snapshot(effective_date="2026-12-31")
    assert snapshot.version_id == "mortality-001"
    assert snapshot.study_hash.startswith("0x")
    assert snapshot.cohort_digest.startswith("0x")
    assert snapshot.summary_stats["cohort_count"] == 2
    assert len(snapshot.cohort_adjustments) == 2


def test_deterministic_sandbox_snapshot_is_privacy_preserving():
    members = [
        Member(wallet="0x1", birth_year=1960, cohort=1960, sex="M"),
        Member(wallet="0x2", birth_year=1962, cohort=1960, sex="F"),
        Member(wallet="0x3", birth_year=1985, cohort=1985, sex="F"),
    ]
    snapshot = deterministic_sandbox_snapshot(members=members, valuation_year=2026)
    publishable = snapshot.to_publishable_dict()
    assert publishable["baseline_model_id"] == "gompertz_makeham_v1"
    assert all("wallet" not in row for row in publishable["cohort_adjustments"])
    assert publishable["study_hash"].startswith("0x")
