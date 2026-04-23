"""Experience Oracle — off-chain mortality learning for Aequitas.

The protocol starts from a transparent baseline mortality prior
(currently Gompertz-Makeham through :mod:`engine.actuarial`) and moves
toward fund-specific experience only as enough verified exposure and
deaths accumulate.

Design boundary:

* Off-chain only:
  - raw member histories
  - death records
  - exposure calculations
  - credibility blending
  - calibration internals
* Publishable on-chain:
  - versioned mortality basis snapshots
  - cohort-level mortality multipliers
  - credibility score
  - effective date
  - study hash / proof hash

The objects below are intentionally cohort-level and serialisable. They
never contain raw personal data.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
import hashlib
import json
import math
from typing import Any, Iterable

import numpy as np

from engine import actuarial as act


BASELINE_MODEL_ID = "gompertz_makeham_v1"


def _sex_loading(sex: str | int) -> float:
    if isinstance(sex, str):
        return {"M": 1.15, "F": 0.88, "U": 1.0}.get(sex.upper(), 1.0)
    return {1: 0.88, 0: 1.15}.get(int(sex), 1.0)


def _baseline_q(age: float, sex: str | int) -> float:
    model = act.GompertzMakeham()
    q = 1.0 - math.exp(-model.mu(float(age) + 0.5))
    return min(1.0, q * _sex_loading(sex))


def _hash_json(payload: dict[str, Any]) -> str:
    blob = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return "0x" + hashlib.sha256(blob).hexdigest()


@dataclass(frozen=True)
class CredibilityConfig:
    """Simple credibility schedule for mortality learning.

    Below the minimum thresholds, the experience study is still visible but
    clearly advisory. Once the study has enough exposure and deaths, the
    weight can rise smoothly toward full credibility.
    """

    min_exposure_years: float = 1_500.0
    min_deaths: int = 12
    full_exposure_years: float = 9_000.0
    full_deaths: int = 75
    advisory_cap: float = 0.25
    max_multiplier_step: float = 0.18
    min_multiplier: float = 0.75
    max_multiplier: float = 1.30


@dataclass(frozen=True)
class CohortExperienceRow:
    cohort: int
    avg_age: float
    retired_share: float
    exposure_years: float
    observed_deaths: int
    expected_deaths: float
    observed_expected: float
    baseline_q: float
    experience_multiplier: float
    credibility_weight: float
    blended_multiplier: float
    stable_enough: bool


@dataclass(frozen=True)
class MortalityBasisSnapshot:
    """Versioned mortality-basis publication object.

    This is the compact, audit-friendly summary that can be published
    on-chain. It contains only aggregated cohort adjustments and proof
    metadata.
    """

    version_id: str
    sequence: int
    baseline_model_id: str
    effective_date: str
    effective_unix: int
    credibility_weight: float
    advisory: bool
    cohort_adjustments: list[CohortExperienceRow]
    summary_stats: dict[str, Any]
    study_hash: str
    cohort_digest: str
    publisher: str = "actuary"

    def multiplier_for(self, cohort: int) -> float:
        for row in self.cohort_adjustments:
            if int(row.cohort) == int(cohort):
                return float(row.blended_multiplier)
        return 1.0

    def cohort_multiplier_map(self) -> dict[int, float]:
        return {
            int(row.cohort): float(row.blended_multiplier)
            for row in self.cohort_adjustments
        }

    def to_publishable_dict(self) -> dict[str, Any]:
        return {
            "version_id": self.version_id,
            "sequence": int(self.sequence),
            "baseline_model_id": self.baseline_model_id,
            "effective_date": self.effective_date,
            "effective_unix": int(self.effective_unix),
            "credibility_weight": float(self.credibility_weight),
            "advisory": bool(self.advisory),
            "cohort_adjustments": [asdict(row) for row in self.cohort_adjustments],
            "summary_stats": dict(self.summary_stats),
            "study_hash": self.study_hash,
            "cohort_digest": self.cohort_digest,
            "publisher": self.publisher,
        }


@dataclass
class ExperienceOracle:
    """Rolling cohort-level experience study accumulator."""

    baseline_model_id: str = BASELINE_MODEL_ID
    credibility: CredibilityConfig = field(default_factory=CredibilityConfig)
    exposure_by_cohort: dict[int, float] = field(default_factory=dict)
    observed_by_cohort: dict[int, int] = field(default_factory=dict)
    expected_by_cohort: dict[int, float] = field(default_factory=dict)
    age_exposure_by_cohort: dict[int, float] = field(default_factory=dict)
    retired_exposure_by_cohort: dict[int, float] = field(default_factory=dict)
    previous_multiplier_by_cohort: dict[int, float] = field(default_factory=dict)
    sequence: int = 0

    def record_period(
        self,
        *,
        cohorts: Iterable[int],
        ages: Iterable[float],
        sexes: Iterable[str | int],
        retired: Iterable[bool],
        death_flags: Iterable[bool],
        exposure_years: float = 1.0,
    ) -> None:
        cohort_arr = np.asarray(list(cohorts), dtype=np.int64)
        if cohort_arr.size == 0:
            return
        age_arr = np.asarray(list(ages), dtype=np.float64)
        sex_arr = np.asarray(list(sexes))
        retired_arr = np.asarray(list(retired), dtype=bool)
        death_arr = np.asarray(list(death_flags), dtype=bool)
        if not (len(age_arr) == len(sex_arr) == len(retired_arr) == len(death_arr) == cohort_arr.size):
            raise ValueError("experience rows must have the same length")

        per_life_exposure = max(float(exposure_years), 0.0)
        for idx, cohort in enumerate(cohort_arr.astype(int)):
            baseline_q = _baseline_q(float(age_arr[idx]), sex_arr[idx])
            exposure = per_life_exposure
            self.exposure_by_cohort[cohort] = self.exposure_by_cohort.get(cohort, 0.0) + exposure
            self.observed_by_cohort[cohort] = self.observed_by_cohort.get(cohort, 0) + int(bool(death_arr[idx]))
            self.expected_by_cohort[cohort] = self.expected_by_cohort.get(cohort, 0.0) + baseline_q * exposure
            self.age_exposure_by_cohort[cohort] = self.age_exposure_by_cohort.get(cohort, 0.0) + float(age_arr[idx]) * exposure
            self.retired_exposure_by_cohort[cohort] = self.retired_exposure_by_cohort.get(cohort, 0.0) + float(bool(retired_arr[idx])) * exposure

    def build_snapshot(
        self,
        *,
        effective_date: str | date,
        publisher: str = "actuary",
    ) -> MortalityBasisSnapshot:
        rows: list[CohortExperienceRow] = []
        total_exposure = 0.0
        total_observed = 0
        total_expected = 0.0

        for cohort in sorted(self.exposure_by_cohort):
            exposure = float(self.exposure_by_cohort.get(cohort, 0.0))
            observed = int(self.observed_by_cohort.get(cohort, 0))
            expected = float(self.expected_by_cohort.get(cohort, 0.0))
            if exposure <= 0:
                continue
            avg_age = float(self.age_exposure_by_cohort.get(cohort, 0.0) / max(exposure, 1e-9))
            retired_share = float(self.retired_exposure_by_cohort.get(cohort, 0.0) / max(exposure, 1e-9))
            baseline_q = expected / max(exposure, 1e-9)
            oe = observed / max(expected, 1e-9)
            experience_multiplier = float(np.clip(
                oe,
                self.credibility.min_multiplier,
                self.credibility.max_multiplier,
            ))
            weight = credibility_weight(
                exposure_years=exposure,
                observed_deaths=observed,
                config=self.credibility,
            )
            prior = float(self.previous_multiplier_by_cohort.get(cohort, 1.0))
            blended = blend_multiplier(
                prior_multiplier=prior,
                experience_multiplier=experience_multiplier,
                weight=weight,
                config=self.credibility,
            )
            stable = exposure >= self.credibility.min_exposure_years and observed >= self.credibility.min_deaths
            rows.append(
                CohortExperienceRow(
                    cohort=int(cohort),
                    avg_age=round(avg_age, 2),
                    retired_share=round(retired_share, 4),
                    exposure_years=round(exposure, 2),
                    observed_deaths=int(observed),
                    expected_deaths=round(expected, 4),
                    observed_expected=round(oe, 4),
                    baseline_q=round(baseline_q, 6),
                    experience_multiplier=round(experience_multiplier, 4),
                    credibility_weight=round(weight, 4),
                    blended_multiplier=round(blended, 4),
                    stable_enough=stable,
                )
            )
            self.previous_multiplier_by_cohort[int(cohort)] = float(blended)
            total_exposure += exposure
            total_observed += observed
            total_expected += expected

        self.sequence += 1
        credibility = (
            float(np.average(
                [row.credibility_weight for row in rows],
                weights=[max(row.exposure_years, 1e-9) for row in rows],
            ))
            if rows else 0.0
        )
        advisory = any(not row.stable_enough for row in rows) if rows else True
        effective_label, effective_unix = _normalise_effective_date(effective_date)
        cohort_payload = [
            {
                "cohort": int(row.cohort),
                "multiplier": float(row.blended_multiplier),
                "credibility": float(row.credibility_weight),
            }
            for row in rows
        ]
        cohort_digest = _hash_json({"cohorts": cohort_payload})
        summary_stats = {
            "cohort_count": len(rows),
            "credible_cohort_count": sum(1 for row in rows if row.stable_enough),
            "total_exposure_years": round(total_exposure, 2),
            "observed_deaths": int(total_observed),
            "expected_deaths": round(total_expected, 4),
            "observed_expected": round(total_observed / max(total_expected, 1e-9), 4),
        }
        study_hash = _hash_json({
            "baseline_model_id": self.baseline_model_id,
            "effective_date": effective_label,
            "summary_stats": summary_stats,
            "cohorts": [asdict(row) for row in rows],
        })
        return MortalityBasisSnapshot(
            version_id=f"mortality-{self.sequence:03d}",
            sequence=self.sequence,
            baseline_model_id=self.baseline_model_id,
            effective_date=effective_label,
            effective_unix=effective_unix,
            credibility_weight=round(credibility, 4),
            advisory=advisory,
            cohort_adjustments=rows,
            summary_stats=summary_stats,
            study_hash=study_hash,
            cohort_digest=cohort_digest,
            publisher=publisher,
        )


def credibility_weight(
    *,
    exposure_years: float,
    observed_deaths: int,
    config: CredibilityConfig,
) -> float:
    """Return a smooth credibility weight in [0, 1]."""

    exposure_share = min(max(float(exposure_years), 0.0) / max(config.full_exposure_years, 1e-9), 1.0)
    death_share = min(max(int(observed_deaths), 0) / max(config.full_deaths, 1), 1.0)
    raw = math.sqrt(exposure_share * death_share)
    if exposure_years < config.min_exposure_years or observed_deaths < config.min_deaths:
        return min(raw, config.advisory_cap)
    return min(raw, 1.0)


def blend_multiplier(
    *,
    prior_multiplier: float,
    experience_multiplier: float,
    weight: float,
    config: CredibilityConfig,
) -> float:
    """Blend the prior and experience smoothly, with a capped step size."""

    target = (1.0 - float(weight)) * float(prior_multiplier) + float(weight) * float(experience_multiplier)
    lower = float(prior_multiplier) - config.max_multiplier_step
    upper = float(prior_multiplier) + config.max_multiplier_step
    return float(np.clip(target, max(lower, config.min_multiplier), min(upper, config.max_multiplier)))


def deterministic_sandbox_snapshot(
    *,
    members: Iterable[Any],
    valuation_year: int,
    effective_date: str | date | None = None,
    publisher: str = "sandbox-actuary",
) -> MortalityBasisSnapshot:
    """Build a deterministic mortality study for the Sandbox.

    The sandbox has no private raw death file, so it constructs a small
    inspectable cohort study from current member ages and synthetic
    exposure/death counts. This keeps the proof layer deterministic while
    still showing how baseline, observed deaths, and credibility interact.
    """

    oracle = ExperienceOracle()
    cohort_stats: dict[int, dict[str, float]] = {}
    for member in members:
        cohort = int(getattr(member, "cohort"))
        age = float(member.age(valuation_year))
        row = cohort_stats.setdefault(cohort, {"members": 0.0, "age_sum": 0.0})
        row["members"] += 1.0
        row["age_sum"] += age
    if not cohort_stats:
        return oracle.build_snapshot(
            effective_date=effective_date or date(valuation_year, 1, 1),
            publisher=publisher,
        )

    for cohort, row in cohort_stats.items():
        members_count = int(row["members"])
        avg_age = float(row["age_sum"] / max(row["members"], 1.0))
        exposure_years = members_count * 9.0
        expected = exposure_years * _baseline_q(avg_age, "U")
        observed = max(0, int(round(expected * (1.05 if avg_age < 55 else 0.96))))
        for i in range(int(round(exposure_years))):
            death_flag = i < observed
            oracle.record_period(
                cohorts=[cohort],
                ages=[avg_age],
                sexes=["U"],
                retired=[avg_age >= 65],
                death_flags=[death_flag],
                exposure_years=1.0,
            )
    return oracle.build_snapshot(
        effective_date=effective_date or date(valuation_year, 1, 1),
        publisher=publisher,
    )


def _normalise_effective_date(value: str | date) -> tuple[str, int]:
    if isinstance(value, date):
        dt = datetime(value.year, value.month, value.day, tzinfo=timezone.utc)
        return value.isoformat(), int(dt.timestamp())
    text = str(value)
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        dt = datetime.strptime(text, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.date().isoformat(), int(dt.timestamp())


__all__ = [
    "BASELINE_MODEL_ID",
    "CredibilityConfig",
    "CohortExperienceRow",
    "ExperienceOracle",
    "MortalityBasisSnapshot",
    "blend_multiplier",
    "credibility_weight",
    "deterministic_sandbox_snapshot",
]
