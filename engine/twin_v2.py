"""Digital Twin V2 simulation engine.

This engine keeps person-level heterogeneity in NumPy arrays, aggregates
results to cohort/fund/population histories for the UI, and preserves the
hybrid Aequitas story by mapping major events to on-chain contracts.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from engine import actuarial as act
from engine.event_process import (
    EventProcessConfig,
    EventProcessState,
    TwinShockEvent,
    sample_year_events,
)
from engine.experience_oracle import ExperienceOracle
from engine.fairness import evaluate_proposal, intergenerational_index, mwr_gini
from engine.fairness_stress import build_cohort_betas, stochastic_cohort_stress
from engine.gas_costs import build_option_b_twin_counts, run_gas_cost_model
from engine.personas import PERSONA_SPECS, persona_catalog, pick_representative_indices
from engine.piu import (
    PiuIndexRule,
    annual_pension_units_from_balance,
    cpi_roll_forward,
    nominal_value_of_pius,
    pius_from_contribution,
)
from engine.population_v2 import (
    POPULATION_STYLES,
    SEX_FEMALE,
    STATUS_ACTIVE,
    STATUS_DECEASED,
    STATUS_RETIRED,
    SyntheticPopulation,
    generate_entrants_v2,
    generate_population_v2,
)


@dataclass(frozen=True)
class BaselinePreset:
    key: str
    label: str
    description: str
    population_style: str
    mean_return: float
    return_vol: float
    salary_growth: float
    inflation: float
    discount_rate: float
    reserve_initial_per_member: float


BASELINE_PRESETS: dict[str, BaselinePreset] = {
    "balanced": BaselinePreset(
        key="balanced",
        label="Balanced society",
        description="Mixed-age workforce with moderate growth, moderate inflation, and a balanced entry flow.",
        population_style="balanced",
        mean_return=0.052,
        return_vol=0.11,
        salary_growth=0.021,
        inflation=0.022,
        discount_rate=0.030,
        reserve_initial_per_member=2_600.0,
    ),
    "growth": BaselinePreset(
        key="growth",
        label="Growth society",
        description="Younger labour force, stronger earnings growth, and faster population renewal.",
        population_style="growth",
        mean_return=0.058,
        return_vol=0.12,
        salary_growth=0.028,
        inflation=0.021,
        discount_rate=0.031,
        reserve_initial_per_member=2_200.0,
    ),
    "mature": BaselinePreset(
        key="mature",
        label="Mature pension society",
        description="Older, more retirement-heavy scheme with slower renewal and a stronger reserve preference.",
        population_style="mature",
        mean_return=0.046,
        return_vol=0.095,
        salary_growth=0.017,
        inflation=0.023,
        discount_rate=0.029,
        reserve_initial_per_member=3_700.0,
    ),
    "fragile": BaselinePreset(
        key="fragile",
        label="Fragile transition",
        description="Lower wage momentum, thinner resilience, and more pressure for corrective policy responses.",
        population_style="fragile",
        mean_return=0.041,
        return_vol=0.13,
        salary_growth=0.014,
        inflation=0.028,
        discount_rate=0.032,
        reserve_initial_per_member=4_100.0,
    ),
}


@dataclass(frozen=True)
class TwinV2Config:
    population_size: int = 10_000
    horizon_years: int = 30
    seed: int = 42
    start_year: int = 2026
    baseline_key: str = "balanced"
    random_events_enabled: bool = True
    event_frequency: float = 1.0
    event_intensity: float = 1.0
    market_crash: bool = True
    inflation_shock: bool = True
    aging_society: bool = True
    unfair_reform: bool = True
    young_stress: bool = True
    stress_scenarios: int = 140


@dataclass
class TwinV2Result:
    config: TwinV2Config
    baseline: BaselinePreset
    annual: pd.DataFrame
    cohort_metrics: pd.DataFrame
    personas: pd.DataFrame
    events: pd.DataFrame
    proposals: pd.DataFrame
    onchain: pd.DataFrame
    mortality_history: pd.DataFrame = field(default_factory=pd.DataFrame)
    mortality_basis: pd.DataFrame = field(default_factory=pd.DataFrame)
    mortality_summary: dict[str, Any] = field(default_factory=dict)
    gas_annual: pd.DataFrame = field(default_factory=pd.DataFrame)
    gas_action_breakdown: pd.DataFrame = field(default_factory=pd.DataFrame)
    gas_comparison: pd.DataFrame = field(default_factory=pd.DataFrame)
    gas_summary: dict[str, Any] = field(default_factory=dict)
    gas_assumptions: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    performance_note: str = ""
    person_level_note: str = ""
    cohort_level_note: str = ""


def baseline_catalog() -> list[dict[str, str]]:
    return [
        {"key": preset.key, "label": preset.label, "description": preset.description}
        for preset in BASELINE_PRESETS.values()
    ]


def _compact_reason(target_cohort: int, before: float, after: float, outcome: dict[str, Any]) -> str:
    max_dev = float(outcome["corridor"]["max_deviation"])
    if outcome["passes"]:
        return (
            f"It passed because the cohort shifts stayed within the fairness corridor. "
            f"The targeted cohort moved from MWR {before:.2f} to {after:.2f}, with max relative deviation {max_dev:.2%}."
        )
    return (
        f"It failed because the targeted cohort {target_cohort} absorbed a disproportionate change. "
        f"Its MWR moved from {before:.2f} to {after:.2f}, breaching the corridor by {max_dev:.2%}."
    )


def _draw_return(rng: np.random.Generator, mean_return: float, vol: float) -> float:
    return float(rng.normal(mean_return, vol))


def _annuity_factor(
    ages: np.ndarray,
    sex: np.ndarray,
    discount_rate: float,
    mortality_multiplier: np.ndarray | None = None,
) -> np.ndarray:
    """Approximate annuity factors via the existing actuarial table."""
    factors = np.zeros_like(ages, dtype=np.float64)
    if mortality_multiplier is None:
        mortality_multiplier = np.ones_like(ages, dtype=np.float64)
    cache: dict[tuple[int, int, float], float] = {}
    for idx, (age, sex_code, mult) in enumerate(
        zip(
            ages.astype(int),
            sex.astype(int),
            np.round(mortality_multiplier.astype(np.float64), 3),
            strict=False,
        )
    ):
        key = (age, sex_code, float(mult))
        if key not in cache:
            sex_loading = 0.88 if sex_code == SEX_FEMALE else 1.15
            table = act.MortalityTable.from_gompertz(
                act.GompertzMakeham(),
                sex_loading=max(0.25, sex_loading * float(mult)),
            )
            rate = act.annuity_rate(table, age, discount_rate)
            cache[key] = 1.0 / max(rate, 1e-6)
        factors[idx] = cache[key]
    return factors


def _cohort_valuation(
    pop: SyntheticPopulation,
    year: int,
    discount_rate: float,
    young_stress_level: float,
    piu_price: float,
    mortality_multiplier_by_cohort: dict[int, float] | None = None,
) -> tuple[pd.DataFrame, dict[int, dict[str, float]]]:
    alive = pop.status != STATUS_DECEASED
    if not alive.any():
        return pd.DataFrame(), {}

    ages = pop.ages(year)[alive]
    cohort = pop.cohort[alive]
    sex = pop.sex[alive]
    status = pop.status[alive]
    asset_balance = pop.balance[alive]
    piu_balance = pop.piu_balance[alive]
    benefit_piu = pop.benefit_piu[alive]
    benefits_paid = pop.benefits_paid[alive]
    contributions = np.maximum(pop.total_contributions[alive], 1e-6)
    retirement_age = pop.retirement_age[alive]
    salary = pop.salary[alive]
    contribution_rate = pop.contribution_rate[alive]
    mortality_multiplier_by_cohort = mortality_multiplier_by_cohort or {}
    mortality_multiplier = np.array(
        [float(mortality_multiplier_by_cohort.get(int(c), 1.0)) for c in cohort],
        dtype=np.float64,
    )

    annuity = _annuity_factor(ages, sex, discount_rate, mortality_multiplier)
    years_to_retire = np.maximum(retirement_age - ages, 0)
    accrual_multiplier = 1.0 + np.clip((ages - 22) / 45.0, 0.0, 1.0) * 0.35
    youth_penalty = 1.0 - young_stress_level * np.clip((retirement_age - ages) / 45.0, 0.0, 1.0) * 0.25
    projected_future_pius = np.where(
        status == STATUS_RETIRED,
        0.0,
        (salary * contribution_rate / max(piu_price, 1e-6)) * np.clip(years_to_retire, 0, 12) * 0.45,
    )
    active_claim_value = (piu_balance + projected_future_pius) * piu_price * accrual_multiplier * youth_penalty
    retired_claim_value = benefit_piu * piu_price * annuity
    entitlement = benefits_paid + np.where(
        status == STATUS_RETIRED,
        retired_claim_value,
        active_claim_value,
    )
    backing = asset_balance + benefits_paid

    unique, inverse = np.unique(cohort, return_inverse=True)
    contrib_sum = np.bincount(inverse, weights=contributions)
    benefit_sum = np.bincount(inverse, weights=entitlement)
    backing_sum = np.bincount(inverse, weights=backing)
    members = np.bincount(inverse)

    rows: list[dict[str, float | int]] = []
    valuation: dict[int, dict[str, float]] = {}
    for idx, cohort_key in enumerate(unique.astype(int)):
        epv_contrib = float(contrib_sum[idx])
        epv_benefit = float(benefit_sum[idx])
        backing_value = float(backing_sum[idx])
        mwr = epv_benefit / max(epv_contrib, 1e-6)
        rows.append(
            {
                "cohort": int(cohort_key),
                "members": int(members[idx]),
                "epv_contributions": epv_contrib,
                "epv_benefits": epv_benefit,
                "backing_value": backing_value,
                "money_worth_ratio": mwr,
            }
        )
        valuation[int(cohort_key)] = {
            "members": int(members[idx]),
            "epv_contributions": epv_contrib,
            "epv_benefits": epv_benefit,
            "backing_value": backing_value,
            "money_worth_ratio": mwr,
        }
    return pd.DataFrame(rows), valuation


def run_twin_v2(cfg: TwinV2Config) -> TwinV2Result:
    baseline = BASELINE_PRESETS.get(cfg.baseline_key, BASELINE_PRESETS["balanced"])
    style = POPULATION_STYLES[baseline.population_style]
    rng = np.random.default_rng(int(cfg.seed))

    pop = generate_population_v2(
        int(cfg.population_size),
        start_year=int(cfg.start_year),
        seed=int(cfg.seed),
        style_key=baseline.population_style,
    )
    persona_indices = pick_representative_indices(pop, int(cfg.start_year))
    reserve = float(cfg.population_size) * baseline.reserve_initial_per_member
    event_state = EventProcessState()
    annual_rows: list[dict[str, Any]] = []
    cohort_rows: list[dict[str, Any]] = []
    persona_rows: list[dict[str, Any]] = []
    proposal_rows: list[dict[str, Any]] = []
    event_rows: list[dict[str, Any]] = []
    onchain_rows: list[dict[str, Any]] = []
    mortality_rows: list[dict[str, Any]] = []
    mortality_basis_rows: list[dict[str, Any]] = []

    next_person_id = pop.size()
    previous_pressure = 0.0
    cpi_index = 100.0
    experience_oracle = ExperienceOracle()
    active_mortality_multipliers: dict[int, float] = {}
    latest_snapshot_summary: dict[str, Any] = {}
    index_rule = PiuIndexRule(
        base_cpi=100.0,
        base_price=1.0,
        expected_inflation=baseline.inflation,
    )

    for year_offset in range(int(cfg.horizon_years)):
        year = int(cfg.start_year) + year_offset
        ages = pop.ages(year)
        alive = pop.status != STATUS_DECEASED
        active = alive & (pop.status == STATUS_ACTIVE)
        retired = alive & (pop.status == STATUS_RETIRED)
        alive_indices_start = np.where(alive)[0]
        alive_cohort_start = pop.cohort[alive_indices_start] if alive_indices_start.size else np.array([], dtype=np.int32)
        alive_age_start = ages[alive_indices_start] if alive_indices_start.size else np.array([], dtype=np.float64)
        alive_sex_start = pop.sex[alive_indices_start] if alive_indices_start.size else np.array([], dtype=np.int8)
        alive_retired_start = pop.status[alive_indices_start] == STATUS_RETIRED if alive_indices_start.size else np.array([], dtype=bool)

        process_cfg = EventProcessConfig(
            enabled=bool(cfg.random_events_enabled),
            frequency=float(cfg.event_frequency),
            intensity=float(cfg.event_intensity),
            market_crash=bool(cfg.market_crash),
            inflation_shock=bool(cfg.inflation_shock),
            aging_society=bool(cfg.aging_society),
            unfair_reform=bool(cfg.unfair_reform),
            young_stress=bool(cfg.young_stress),
        )
        year_events, event_state, impacts = sample_year_events(
            year=year,
            rng=rng,
            config=process_cfg,
            state=event_state,
            pressure=previous_pressure,
        )

        mean_return = baseline.mean_return - float(impacts["aging_drift"]) * 0.018
        inflation_rate = baseline.inflation + float(impacts["inflation_extra"])
        salary_growth = baseline.salary_growth - float(impacts["aging_drift"]) * 0.005 + inflation_rate * 0.25
        entrant_rate = style.entrant_rate * max(0.25, 1.0 - float(impacts["aging_drift"]) * 1.4)
        realized_return = _draw_return(rng, mean_return, baseline.return_vol) + float(impacts["return_shock"])
        realized_return = float(np.clip(realized_return, -0.55, 0.30))
        cpi_index = cpi_roll_forward(cpi_index, inflation_rate)
        piu_price = index_rule.price_for_cpi(cpi_index)

        if active.any():
            age_bonus = np.clip((ages[active] - 22) / 40.0, 0.0, 1.0) * 0.006
            pop.salary[active] *= np.maximum(0.92, 1.0 + salary_growth + age_bonus)
            contributions = pop.salary[active] * pop.contribution_rate[active]
            pius_minted = contributions / max(piu_price, 1e-6)
            pop.total_contributions[active] += contributions
            pop.piu_balance[active] += pius_minted
            pop.balance[active] += contributions
            contribution_total = float(contributions.sum())
            piu_minted_total = float(pius_minted.sum())
        else:
            contribution_total = 0.0
            piu_minted_total = 0.0

        reserve += contribution_total * style.reserve_capture
        pop.balance[alive] *= 1.0 + realized_return
        reserve *= 1.0 + realized_return

        newly_retired = active & (ages >= pop.retirement_age)
        if newly_retired.any():
            retiree_factors = _annuity_factor(ages[newly_retired], pop.sex[newly_retired], baseline.discount_rate)
            pop.benefit_piu[newly_retired] = np.maximum(
                pop.piu_balance[newly_retired] / np.maximum(retiree_factors, 1e-6),
                (pop.salary[newly_retired] * 0.18) / max(piu_price, 1e-6),
            )
            pop.annual_benefit[newly_retired] = pop.benefit_piu[newly_retired] * piu_price
            pop.piu_balance[newly_retired] = 0.0
            pop.status[newly_retired] = STATUS_RETIRED

        retired = (pop.status == STATUS_RETIRED) & (pop.status != STATUS_DECEASED)
        if retired.any():
            pop.annual_benefit[retired] = pop.benefit_piu[retired] * piu_price
            payable = pop.annual_benefit[retired]
            from_balance = np.minimum(pop.balance[retired], payable)
            shortfall = payable - from_balance
            reserve_draw = min(float(shortfall.sum()), reserve)
            reserve -= reserve_draw
            balance_shortfall = shortfall.copy()
            if shortfall.sum() > 0 and reserve_draw > 0:
                balance_shortfall *= 1.0 - (reserve_draw / float(shortfall.sum()))
            paid = payable - balance_shortfall
            pop.balance[retired] -= from_balance
            pop.benefits_paid[retired] += paid
            benefit_total = float(paid.sum())
        else:
            benefit_total = 0.0
            reserve_draw = 0.0

        alive = pop.status != STATUS_DECEASED
        ages = pop.ages(year)
        alive_indices = np.where(alive)[0]
        if alive_indices.size:
            mortality_base = act.GompertzMakeham()
            mu = mortality_base.A + mortality_base.B * (mortality_base.c ** (ages[alive_indices].astype(float) + 0.5))
            mortality_multiplier = max(0.72, 1.0 - float(impacts["aging_drift"]) * 0.45)
            learned_multiplier = np.array(
                [float(active_mortality_multipliers.get(int(c), 1.0)) for c in pop.cohort[alive_indices]],
                dtype=np.float64,
            )
            q = 1.0 - np.exp(
                -mu
                * mortality_multiplier
                * learned_multiplier
                * np.where(pop.sex[alive_indices] == SEX_FEMALE, 0.92, 1.08)
            )
            death_mask = rng.random(alive_indices.shape[0]) < np.clip(q, 0.0, 0.35)
            deaths = alive_indices[death_mask]
        else:
            deaths = np.array([], dtype=np.int64)
        if deaths.size:
            reserve += float(pop.balance[deaths].sum()) * 0.18
            pop.balance[deaths] = 0.0
            pop.piu_balance[deaths] = 0.0
            pop.benefit_piu[deaths] = 0.0
            pop.annual_benefit[deaths] = 0.0
            pop.status[deaths] = STATUS_DECEASED

        if alive_indices_start.size:
            start_index_lookup = {int(idx): pos for pos, idx in enumerate(alive_indices_start)}
            death_flags = np.zeros(alive_indices_start.shape[0], dtype=bool)
            for idx in deaths:
                pos = start_index_lookup.get(int(idx))
                if pos is not None:
                    death_flags[pos] = True
            experience_oracle.record_period(
                cohorts=alive_cohort_start,
                ages=alive_age_start,
                sexes=alive_sex_start,
                retired=alive_retired_start,
                death_flags=death_flags,
                exposure_years=1.0,
            )
            snapshot = experience_oracle.build_snapshot(
                effective_date=f"{year}-12-31",
                publisher="digital-twin",
            )
            active_mortality_multipliers = snapshot.cohort_multiplier_map()
            latest_snapshot_summary = snapshot.summary_stats
            mortality_rows.append(
                {
                    "year": year,
                    "version_id": snapshot.version_id,
                    "credibility_weight": round(float(snapshot.credibility_weight), 4),
                    "credibility_pct": round(float(snapshot.credibility_weight) * 100.0, 2),
                    "advisory": snapshot.advisory,
                    "cohort_count": int(snapshot.summary_stats.get("cohort_count", 0) or 0),
                    "credible_cohort_count": int(snapshot.summary_stats.get("credible_cohort_count", 0) or 0),
                    "total_exposure_years": float(snapshot.summary_stats.get("total_exposure_years", 0.0) or 0.0),
                    "observed_deaths": int(snapshot.summary_stats.get("observed_deaths", 0) or 0),
                    "expected_deaths": float(snapshot.summary_stats.get("expected_deaths", 0.0) or 0.0),
                    "observed_expected": float(snapshot.summary_stats.get("observed_expected", 1.0) or 1.0),
                    "average_multiplier": round(
                        float(np.mean([row.blended_multiplier for row in snapshot.cohort_adjustments])) if snapshot.cohort_adjustments else 1.0,
                        4,
                    ),
                    "study_hash": snapshot.study_hash,
                }
            )
            mortality_basis_rows.extend(
                [
                    {
                        "year": year,
                        "version_id": snapshot.version_id,
                        "cohort": int(row.cohort),
                        "avg_age": float(row.avg_age),
                        "retired_share": float(row.retired_share),
                        "exposure_years": float(row.exposure_years),
                        "observed_deaths": int(row.observed_deaths),
                        "expected_deaths": float(row.expected_deaths),
                        "observed_expected": float(row.observed_expected),
                        "credibility_weight": float(row.credibility_weight),
                        "experience_multiplier": float(row.experience_multiplier),
                        "blended_multiplier": float(row.blended_multiplier),
                        "stable_enough": bool(row.stable_enough),
                    }
                    for row in snapshot.cohort_adjustments
                ]
            )
            onchain_rows.append(
                {
                    "year": year,
                    "simulation": "Mortality basis snapshot ready",
                    "contract": "MortalityBasisOracle",
                    "action": "publishBasis",
                    "classification": "advisory" if snapshot.advisory else "executable",
                    "detail": (
                        f"Experience across {snapshot.summary_stats.get('cohort_count', 0)} cohorts produced "
                        f"mortality basis {snapshot.version_id} with credibility {snapshot.credibility_weight:.1%}. "
                        "Only cohort multipliers and a study hash would be published on chain; raw death records stay off chain."
                    ),
                }
            )
            if year_offset == 0 or len(mortality_rows) < 2 or abs(
                mortality_rows[-1]["average_multiplier"] - mortality_rows[-2]["average_multiplier"]
            ) >= 0.02:
                event_rows.append(
                    {
                        "year": year,
                        "lane": "Mortality",
                        "label": "Experience-based mortality update",
                        "detail": (
                            f"The scheme blended the Gompertz prior with observed experience. "
                            f"Credibility is now {snapshot.credibility_weight:.1%}, so the active mortality basis "
                            f"uses cohort multipliers around {mortality_rows[-1]['average_multiplier']:.2f}x baseline."
                        ),
                        "severity": "warn" if snapshot.advisory else "good",
                        "contract": "MortalityBasisOracle",
                        "action": "publishBasis",
                        "classification": "advisory" if snapshot.advisory else "executable",
                    }
                )

        entrant_mean = max(0.0, cfg.population_size * entrant_rate)
        entrant_count = int(rng.poisson(entrant_mean))
        if entrant_count > 0:
            entrants = generate_entrants_v2(
                entrant_count,
                year=year,
                rng=rng,
                style_key=baseline.population_style,
                id_offset=next_person_id,
            )
            next_person_id += entrants.size()
            pop.append(entrants)

        cohort_df, cohort_valuation = _cohort_valuation(
            pop,
            year,
            baseline.discount_rate,
            float(impacts["young_stress_level"]),
            float(piu_price),
            active_mortality_multipliers,
        )

        gini = 0.0
        intergen = 0.0
        funded_ratio = 1.0
        scheme_mwr = 0.0
        stress_pass_rate = 1.0
        p95_gini = 0.0
        youngest_poor_rate = 0.0
        selected_slope = 0.45 + float(impacts["young_stress_level"]) * 0.40
        stress_rows: dict[int, float] = {}

        if cohort_valuation:
            mwrs = {c: row["money_worth_ratio"] for c, row in cohort_valuation.items()}
            gini = float(mwr_gini(mwrs))
            intergen = float(intergenerational_index(mwrs))
            epv_contrib = sum(row["epv_contributions"] for row in cohort_valuation.values())
            epv_benefit = sum(row["epv_benefits"] for row in cohort_valuation.values())
            funded_ratio = (float(pop.balance.sum()) + reserve) / max(epv_benefit, 1e-6)
            scheme_mwr = epv_benefit / max(epv_contrib, 1e-6)
            if len(cohort_valuation) >= 2:
                ordered = sorted(cohort_valuation)
                betas = build_cohort_betas(ordered, slope=min(0.95, selected_slope))
                stress = stochastic_cohort_stress(
                    cohort_valuation,
                    n_scenarios=max(80, min(int(cfg.stress_scenarios), 220)),
                    factor_sigma=max(0.05, baseline.return_vol),
                    idiosyncratic_sigma=0.03,
                    betas=betas,
                    generational_slope=min(0.95, selected_slope),
                    corridor_delta=0.05,
                    youngest_poor_threshold=0.92,
                    seed=int(cfg.seed) + year_offset,
                )
                stress_pass_rate = float(stress["corridor_pass_rate"])
                p95_gini = float(stress["p95_gini"])
                youngest_poor_rate = float(stress["youngest_poor_rate"])
                stress_rows = {int(c): float(stress["worst_cohort_freq"].get(c, 0.0)) for c in ordered}

        proposals_this_year = 0
        if bool(impacts["trigger_unfair_reform"]) and cohort_valuation:
            ordered = sorted(cohort_valuation)
            if ordered:
                target = int(ordered[-1] if impacts["young_stress_level"] else ordered[-1 if funded_ratio < 0.95 else max(0, len(ordered) - 2)])
                cut = float(np.clip(1.0 - (0.02 + previous_pressure * 0.04 + cfg.event_intensity * 0.02), 0.88, 0.99))
                proposal_multipliers = {c: 1.0 for c in ordered}
                proposal_multipliers[target] = cut
                outcome = evaluate_proposal(cohort_valuation, proposal_multipliers, delta=0.05)
                before = float(outcome["mwr_before"][target])
                after = float(outcome["mwr_after"][target])
                pass_fail = bool(outcome["passes"])
                reason = _compact_reason(target, before, after, outcome)
                proposal_rows.append(
                    {
                        "year": year,
                        "proposal": f"Rebalance cohort {target}",
                        "target_cohort": target,
                        "before_mwr": round(before, 3),
                        "after_mwr": round(after, 3),
                        "passed": "PASS" if pass_fail else "FAIL",
                        "reason": reason,
                        "contract": "FairnessGate",
                        "action": "submitAndEvaluate",
                        "classification": "executable" if pass_fail else "proposed",
                    }
                )
                onchain_rows.append(
                    {
                        "year": year,
                        "simulation": "Governance proposal evaluated",
                        "contract": "FairnessGate",
                        "action": "submitAndEvaluate",
                        "classification": "executable" if pass_fail else "proposed",
                        "detail": reason,
                    }
                )
                event_rows.append(
                    {
                        "year": year,
                        "lane": "Governance",
                        "label": "Unfair reform proposal",
                        "detail": reason,
                        "severity": "good" if pass_fail else "bad",
                        "contract": "FairnessGate",
                        "action": "submitAndEvaluate",
                        "classification": "executable" if pass_fail else "proposed",
                    }
                )
                proposals_this_year = 1

        if reserve_draw > 0:
            onchain_rows.append(
                {
                    "year": year,
                    "simulation": "Reserve released to honour pensions",
                    "contract": "BackstopVault",
                    "action": "release",
                    "classification": "executable",
                    "detail": f"The reserve covered about £{reserve_draw:,.0f} of benefit shortfall.",
                }
            )

        onchain_rows.append(
            {
                "year": year,
                "simulation": "PIU price published from CPI",
                "contract": "CohortLedger",
                "action": "setPiuPrice",
                "classification": "executable",
                "detail": (
                    f"CPI moved to {cpi_index:.1f}, so the protocol would publish a PIU price of "
                    f"£{piu_price:,.3f}. Higher CPI means the same nominal contribution buys fewer PIUs."
                ),
            }
        )

        for event in year_events:
            event_rows.append(
                {
                    "year": event.year,
                    "lane": "Events",
                    "label": event.label,
                    "detail": event.detail,
                    "severity": event.severity,
                    "contract": event.contract,
                    "action": event.action,
                    "classification": event.classification,
                }
            )
            onchain_rows.append(
                {
                    "year": event.year,
                    "simulation": event.label,
                    "contract": event.contract,
                    "action": event.action,
                    "classification": event.classification,
                    "detail": event.detail,
                }
            )

        if contribution_total > 0:
            onchain_rows.append(
                {
                    "year": year,
                    "simulation": "Annual contributions posted",
                    "contract": "CohortLedger",
                    "action": "contribute",
                    "classification": "advisory",
                    "detail": (
                        f"Members paid about £{contribution_total:,.0f} and minted roughly {piu_minted_total:,.0f} PIUs "
                        f"at the current price of £{piu_price:,.3f}."
                    ),
                }
            )

        for spec in PERSONA_SPECS:
            idx = persona_indices.get(spec.key)
            if idx is None or idx >= pop.size():
                continue
            persona_rows.append(
                {
                    "year": year,
                    "key": spec.key,
                    "label": spec.label,
                    "description": spec.description,
                    "age": int(pop.ages(year)[idx]),
                    "retirement_age": int(pop.retirement_age[idx]),
                    "status": ["Active", "Retired", "Deceased"][int(pop.status[idx])],
                    "salary": round(float(pop.salary[idx]), 2),
                    "balance": round(float(pop.balance[idx]), 2),
                    "piu_balance": round(float(pop.piu_balance[idx]), 4),
                    "piu_price": round(float(piu_price), 4),
                    "nominal_piu_value": round(nominal_value_of_pius(float(pop.piu_balance[idx]), piu_price), 2),
                    "benefit_piu": round(float(pop.benefit_piu[idx]), 4),
                    "annual_benefit": round(float(pop.annual_benefit[idx]), 2),
                    "contributions_paid": round(float(pop.total_contributions[idx]), 2),
                    "benefits_received": round(float(pop.benefits_paid[idx]), 2),
                }
            )

        active_count = int(np.sum(pop.status == STATUS_ACTIVE))
        retired_count = int(np.sum(pop.status == STATUS_RETIRED))
        deceased_count = int(np.sum(pop.status == STATUS_DECEASED))
        population_total = active_count + retired_count
        avg_age = float(np.mean(pop.ages(year)[pop.status != STATUS_DECEASED])) if population_total else 0.0
        avg_salary = float(np.mean(pop.salary[pop.status == STATUS_ACTIVE])) if active_count else 0.0
        reserve_ratio = reserve / max(float(pop.balance.sum()) + reserve, 1e-6)
        indexed_liability = sum(row["epv_benefits"] for row in cohort_valuation.values()) if cohort_valuation else 0.0
        accrued_pius = float(pop.piu_balance[pop.status != STATUS_DECEASED].sum())
        pension_units = float(pop.benefit_piu[pop.status == STATUS_RETIRED].sum())

        annual_rows.append(
            {
                "year": year,
                "population_total": population_total,
                "active_count": active_count,
                "retired_count": retired_count,
                "deceased_count": deceased_count,
                "entrant_count": entrant_count,
                "retirement_count": int(newly_retired.sum()),
                "death_count": int(deaths.size),
                "average_age": round(avg_age, 2),
                "average_salary": round(avg_salary, 2),
                "fund_nav": round(float(pop.balance.sum()), 2),
                "reserve": round(float(reserve), 2),
                "contributions": round(contribution_total, 2),
                "benefits": round(benefit_total, 2),
                "piu_minted": round(float(piu_minted_total), 4),
                "accrued_pius": round(accrued_pius, 4),
                "pension_units": round(pension_units, 4),
                "cpi_index": round(float(cpi_index), 4),
                "piu_price": round(float(piu_price), 4),
                "pius_per_1000": round(float(piu_minted_total) * 1000.0 / max(contribution_total, 1e-6), 4),
                "indexed_liability": round(float(indexed_liability), 2),
                "mortality_credibility": round(float(mortality_rows[-1]["credibility_weight"]) if mortality_rows else 0.0, 4),
                "mortality_multiplier": round(float(mortality_rows[-1]["average_multiplier"]) if mortality_rows else 1.0, 4),
                "mortality_observed_expected": round(float(mortality_rows[-1]["observed_expected"]) if mortality_rows else 1.0, 4),
                "return_rate": round(realized_return, 4),
                "inflation_rate": round(inflation_rate, 4),
                "funded_ratio": round(funded_ratio, 4),
                "scheme_mwr": round(scheme_mwr, 4),
                "gini": round(gini, 4),
                "intergen_index": round(intergen, 4),
                "stress_pass_rate": round(stress_pass_rate, 4),
                "stress_p95_gini": round(p95_gini, 4),
                "youngest_poor_rate": round(youngest_poor_rate, 4),
                "event_pressure": round(previous_pressure, 4),
                "reserve_ratio": round(reserve_ratio, 4),
                "proposals_generated": proposals_this_year,
            }
        )

        if not cohort_df.empty:
            cohort_df = cohort_df.copy()
            cohort_df["year"] = year
            cohort_df["stress_load"] = cohort_df["cohort"].map(lambda c: round(stress_rows.get(int(c), 0.0), 4))
            cohort_df["per_member_epv"] = cohort_df["epv_benefits"] / cohort_df["members"].clip(lower=1)
            cohort_rows.extend(cohort_df.to_dict("records"))

        previous_pressure = float(
            np.clip(
                max(0.0, 1.0 - funded_ratio) * 0.8
                + max(0.0, gini - 0.08) * 3.0
                + max(0.0, 0.78 - stress_pass_rate) * 0.7
                + max(0.0, 0.05 - reserve_ratio) * 4.0,
                0.0,
                1.5,
            )
        )

    annual_df = pd.DataFrame(annual_rows)
    cohort_df_all = pd.DataFrame(cohort_rows)
    persona_df = pd.DataFrame(persona_rows)
    event_df = pd.DataFrame(event_rows)
    proposal_df = pd.DataFrame(proposal_rows)
    onchain_df = pd.DataFrame(onchain_rows)
    mortality_history_df = pd.DataFrame(mortality_rows)
    mortality_basis_df = pd.DataFrame(mortality_basis_rows)
    gas_result = run_gas_cost_model(
        build_option_b_twin_counts(
            annual_df,
            starting_population=cfg.population_size,
            cohort_count=int(cohort_df_all["cohort"].nunique()) if not cohort_df_all.empty else 0,
        ),
        preset_key="ethereum",
    )

    assumptions = [
        "Population heterogeneity is simulated at person level using vectorized NumPy arrays.",
        "Contributions buy CPI-linked PIUs, while funding assets are tracked separately so inflation can create real liability pressure.",
        "Fairness and stress are evaluated at cohort level using aggregate contribution and indexed entitlement estimates.",
        "Mortality starts from a baseline Gompertz-Makeham prior and then blends toward fund experience through a cohort-level credibility weight.",
        "Only mortality-basis snapshots, cohort multipliers, and study hashes belong on chain; raw death records and private member data stay off chain.",
        "Inflation shocks can persist across years, and each CPI move implies a publishable PIU price update on CohortLedger.",
        "Backstop releases occur when benefit payments exceed member balances and reserve support is needed.",
        *gas_result.assumptions,
    ]

    return TwinV2Result(
        config=cfg,
        baseline=baseline,
        annual=annual_df,
        cohort_metrics=cohort_df_all,
        personas=persona_df,
        events=event_df,
        proposals=proposal_df,
        onchain=onchain_df,
        mortality_history=mortality_history_df,
        mortality_basis=mortality_basis_df,
        mortality_summary=latest_snapshot_summary,
        gas_annual=gas_result.annual,
        gas_action_breakdown=gas_result.action_breakdown,
        gas_comparison=gas_result.preset_comparison,
        gas_summary=gas_result.summary,
        gas_assumptions=gas_result.assumptions,
        assumptions=assumptions,
        performance_note=(
            "The simulator keeps person state in arrays and only materialises aggregate history, cohort summaries, "
            "and a small set of representative personas for the UI. That keeps 100k-member runs practical."
        ),
        person_level_note=(
            "Person-level: age, salary, contribution rate, PIU balance, funding balance, pension-unit conversion, benefits, and mortality."
        ),
        cohort_level_note=(
            "Cohort-level: indexed liabilities, MWR, fairness dispersion, inflation stress, proposal evaluation, and on-chain policy mapping."
        ),
    )


__all__ = [
    "BASELINE_PRESETS",
    "BaselinePreset",
    "TwinV2Config",
    "TwinV2Result",
    "baseline_catalog",
    "run_twin_v2",
]
