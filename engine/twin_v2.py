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
from engine.investment_policy import (
    MIN_VOTERS_FOR_STRICT_CAP,
    MODEL_PORTFOLIOS,
    SimulationPolicyValidationInputs,
    allocation_hash,
    compute_vote_snapshot_from_inputs,
    portfolio_order,
    simulate_member_portfolio_preference,
    validate_simulated_policy,
)
from engine.personas import PERSONA_SPECS, persona_catalog, pick_representative_indices
from engine.piu import (
    DEFAULT_SMOOTHING_WEIGHT,
    annual_pension_units_from_balance,
    cpi_roll_forward,
    nominal_value_of_pius,
    pius_from_contribution,
    update_piu_price,
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
    investment_voting_enabled: bool = True
    investment_ballot_interval_years: int = 4
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
    investment_ballots: pd.DataFrame = field(default_factory=pd.DataFrame)
    investment_policy_history: pd.DataFrame = field(default_factory=pd.DataFrame)
    investment_vote_snapshot: pd.DataFrame = field(default_factory=pd.DataFrame)
    investment_summary: dict[str, Any] = field(default_factory=dict)
    investment_effects: pd.DataFrame = field(default_factory=pd.DataFrame)
    investment_onchain: pd.DataFrame = field(default_factory=pd.DataFrame)
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
    retired_claim_value = benefit_piu * annuity
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


def _default_investment_policy_key(baseline_key: str) -> str:
    if baseline_key == "growth":
        return "growth"
    if baseline_key == "fragile":
        return "defensive"
    return "balanced"


def _policy_path_settings(policy_key: str) -> dict[str, float]:
    portfolio = MODEL_PORTFOLIOS[policy_key]
    neutral = MODEL_PORTFOLIOS["balanced"]
    return {
        "mean_return_shift": (portfolio.expected_return - neutral.expected_return) * 0.9,
        "crash_multiplier": 1.0 + max(0.0, portfolio.stress_drawdown - neutral.stress_drawdown) * 2.4,
        "inflation_buffer": (portfolio.inflation_hedge - neutral.inflation_hedge) * 0.6,
        "fairness_bias": portfolio.fairness_pressure - neutral.fairness_pressure,
    }


def _ballot_due(cfg: TwinV2Config, year_offset: int) -> bool:
    interval = max(2, int(cfg.investment_ballot_interval_years))
    return bool(cfg.investment_voting_enabled) and year_offset >= 1 and (year_offset % interval == 0)


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
    investment_ballot_rows: list[dict[str, Any]] = []
    investment_policy_rows: list[dict[str, Any]] = []
    investment_vote_snapshot_rows: list[dict[str, Any]] = []
    investment_effect_rows: list[dict[str, Any]] = []
    investment_onchain_rows: list[dict[str, Any]] = []

    next_person_id = pop.size()
    previous_pressure = 0.0
    cpi_index = 100.0
    experience_oracle = ExperienceOracle()
    active_mortality_multipliers: dict[int, float] = {}
    latest_snapshot_summary: dict[str, Any] = {}
    piu_smoothing_weight = DEFAULT_SMOOTHING_WEIGHT
    piu_price = 1.0
    raw_piu_price = 1.0
    active_pool_nav = float(pop.balance[pop.status == STATUS_ACTIVE].sum())
    total_active_piu_supply = float(pop.piu_balance[pop.status == STATUS_ACTIVE].sum())
    initial_piu_state = update_piu_price(
        active_pool_nav,
        total_active_piu_supply,
        piu_price,
        piu_smoothing_weight,
        initial_price=1.0,
    )
    raw_piu_price = float(initial_piu_state.raw_piu_price)
    piu_price = float(initial_piu_state.published_piu_price)
    active_policy_key = _default_investment_policy_key(cfg.baseline_key)
    active_policy_settings = _policy_path_settings(active_policy_key)
    pending_policy_key = active_policy_key
    pending_effective_year = int(cfg.start_year)

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

        if year >= pending_effective_year:
            active_policy_key = pending_policy_key
            active_policy_settings = _policy_path_settings(active_policy_key)

        mean_return = (
            baseline.mean_return
            + active_policy_settings["mean_return_shift"]
            - float(impacts["aging_drift"]) * 0.018
        )
        inflation_rate = max(
            0.0,
            baseline.inflation
            + float(impacts["inflation_extra"])
            - active_policy_settings["inflation_buffer"] * max(0.0, float(impacts["inflation_extra"])),
        )
        salary_growth = baseline.salary_growth - float(impacts["aging_drift"]) * 0.005 + inflation_rate * 0.25
        entrant_rate = style.entrant_rate * max(0.25, 1.0 - float(impacts["aging_drift"]) * 1.4)
        realized_return = _draw_return(rng, mean_return, baseline.return_vol) + (
            float(impacts["return_shock"]) * active_policy_settings["crash_multiplier"]
        )
        realized_return = float(np.clip(realized_return, -0.55, 0.30))
        cpi_index = cpi_roll_forward(cpi_index, inflation_rate)

        contribution_snapshot = np.array([], dtype=np.float64)
        contribution_member_ids = np.array([], dtype=np.int64)
        contribution_ages = np.array([], dtype=np.float64)
        contribution_years_to_retirement = np.array([], dtype=np.float64)
        if active.any():
            age_bonus = np.clip((ages[active] - 22) / 40.0, 0.0, 1.0) * 0.006
            pop.salary[active] *= np.maximum(0.92, 1.0 + salary_growth + age_bonus)
            contributions = pop.salary[active] * pop.contribution_rate[active]
            contribution_snapshot = contributions.astype(np.float64, copy=True)
            contribution_member_ids = pop.person_id[active].astype(np.int64, copy=True)
            contribution_ages = ages[active].astype(np.float64, copy=True)
            contribution_years_to_retirement = np.maximum(
                pop.retirement_age[active] - ages[active],
                0,
            ).astype(np.float64, copy=True)
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

        active_pool_nav = float(pop.balance[active].sum())
        total_active_piu_supply = float(pop.piu_balance[active].sum())
        previous_piu_price = float(piu_price)
        piu_state = update_piu_price(
            active_pool_nav,
            total_active_piu_supply,
            previous_piu_price,
            piu_smoothing_weight,
            initial_price=1.0,
        )
        raw_piu_price = float(piu_state.raw_piu_price)
        piu_price = float(piu_state.published_piu_price)

        newly_retired = active & (ages >= pop.retirement_age)
        pius_burned_total = 0.0
        retirement_capital_total = 0.0
        annual_benefit_opened_total = 0.0
        if newly_retired.any():
            retiree_factors = _annuity_factor(ages[newly_retired], pop.sex[newly_retired], baseline.discount_rate)
            retirement_capital = pop.piu_balance[newly_retired] * max(piu_price, 1e-6)
            annual_benefit_opened = np.maximum(
                retirement_capital / np.maximum(retiree_factors, 1e-6),
                pop.salary[newly_retired] * 0.18,
            )
            pius_burned_total = float(pop.piu_balance[newly_retired].sum())
            retirement_capital_total = float(retirement_capital.sum())
            annual_benefit_opened_total = float(annual_benefit_opened.sum())
            pop.benefit_piu[newly_retired] = annual_benefit_opened
            pop.annual_benefit[newly_retired] = annual_benefit_opened
            pop.balance[newly_retired] = retirement_capital
            pop.piu_balance[newly_retired] = 0.0
            pop.status[newly_retired] = STATUS_RETIRED

        retired = (pop.status == STATUS_RETIRED) & (pop.status != STATUS_DECEASED)
        if retired.any():
            pop.annual_benefit[retired] = pop.benefit_piu[retired]
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

        if abs(piu_price - previous_piu_price) > 1e-6 or year_offset == 0:
            event_rows.append(
                {
                    "year": year,
                    "lane": "PIU",
                    "label": "PIU price updated",
                    "detail": (
                        f"The active pool NAV was £{active_pool_nav:,.0f} against {total_active_piu_supply:,.0f} active PIUs. "
                        f"Raw NAV price was £{raw_piu_price:.3f}; the smoothed published price moved to £{piu_price:.3f}."
                    ),
                    "severity": "good" if piu_price >= previous_piu_price else "warn",
                    "contract": "CohortLedger",
                    "action": "setPiuPrice",
                    "classification": "executable",
                }
            )
        onchain_rows.append(
            {
                "year": year,
                "simulation": "Smoothed PIU price published from fund NAV",
                "contract": "CohortLedger",
                "action": "setPiuPrice",
                "classification": "executable",
                "detail": (
                    f"Active accumulation NAV was £{active_pool_nav:,.0f} and active PIU supply was "
                    f"{total_active_piu_supply:,.0f}. Raw NAV price £{raw_piu_price:.3f} was smoothed "
                    f"with weight {piu_smoothing_weight:.1f} into a published price of £{piu_price:.3f}."
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
                        f"Members paid about £{contribution_total:,.0f} into the active pool and minted roughly "
                        f"{piu_minted_total:,.0f} non-transferable PIUs at the published price of £{piu_price:,.3f}."
                    ),
                }
            )
            event_rows.append(
                {
                    "year": year,
                    "lane": "PIU",
                    "label": "PIUs minted",
                    "detail": f"Contributions entered the active pool and minted {piu_minted_total:,.0f} PIUs at £{piu_price:.3f}.",
                    "severity": "good",
                    "contract": "CohortLedger",
                    "action": "contribute",
                    "classification": "advisory",
                }
            )

        if pius_burned_total > 0:
            event_rows.append(
                {
                    "year": year,
                    "lane": "PIU",
                    "label": "PIUs burned for retirement",
                    "detail": (
                        f"New retirees consumed {pius_burned_total:,.0f} PIUs, creating £{retirement_capital_total:,.0f} "
                        f"of retirement capital and £{annual_benefit_opened_total:,.0f} of annual benefits."
                    ),
                    "severity": "good",
                    "contract": "VestaRouter",
                    "action": "openRetirement",
                    "classification": "executable",
                }
            )
            onchain_rows.append(
                {
                    "year": year,
                    "simulation": "Retirement conversion opened",
                    "contract": "VestaRouter",
                    "action": "openRetirement",
                    "classification": "executable",
                    "detail": (
                        f"PIUs were burned or locked, retirement capital was committed, and BenefitStreamer would open "
                        f"the pension stream using the actuarial annuity conversion."
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
                "raw_piu_price": round(float(raw_piu_price), 4),
                "published_piu_price": round(float(piu_price), 4),
                "active_pool_nav": round(float(active_pool_nav), 2),
                "total_active_piu_supply": round(float(total_active_piu_supply), 4),
                "piu_smoothing_weight": round(float(piu_smoothing_weight), 4),
                "pius_burned": round(float(pius_burned_total), 4),
                "retirement_capital": round(float(retirement_capital_total), 2),
                "annual_benefit_opened": round(float(annual_benefit_opened_total), 2),
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

        current_pressure = float(
            np.clip(
                max(0.0, 1.0 - funded_ratio) * 0.8
                + max(0.0, gini - 0.08) * 3.0
                + max(0.0, 0.78 - stress_pass_rate) * 0.7
                + max(0.0, 0.05 - reserve_ratio) * 4.0,
                0.0,
                1.5,
            )
        )

        ballot_status = "No ballot"
        policy_next_year = active_policy_key
        if _ballot_due(cfg, year_offset) and contribution_member_ids.size >= MIN_VOTERS_FOR_STRICT_CAP:
            event_rows.append(
                {
                    "year": year,
                    "lane": "Governance",
                    "label": "Investment ballot opened",
                    "detail": (
                        f"Active contributors in {year} opened a model-portfolio ballot. "
                        "Each voter received one base vote plus a capped concave boost from this year's contribution flow."
                    ),
                    "severity": "good",
                    "contract": "InvestmentPolicyBallot",
                    "action": "createBallot",
                    "classification": "proposed",
                }
            )

            voter_ids = [f"sim-{int(pid)}" for pid in contribution_member_ids.tolist()]
            weight_rows = compute_vote_snapshot_from_inputs(voter_ids, contribution_snapshot.tolist())
            retiree_share = retired_count / max(population_total, 1)
            near_retire_share = float(np.mean(contribution_years_to_retirement <= 10.0)) if contribution_years_to_retirement.size else 0.0
            validation_inputs = SimulationPolicyValidationInputs(
                funded_ratio_before=funded_ratio,
                gini_before=gini,
                intergen_before=intergen if intergen > 0 else 1.0,
                stress_pass_rate_before=stress_pass_rate,
                expected_inflation=inflation_rate,
                retiree_share=retiree_share,
                near_retire_share=near_retire_share,
            )
            tallies = {key: 0 for key in portfolio_order()}
            counts = {key: 0 for key in portfolio_order()}
            top_weights = sorted(weight_rows, key=lambda row: row.published_weight, reverse=True)[:12]
            top_weight_wallets = {row.wallet for row in top_weights}
            preference_rows: list[dict[str, Any]] = []
            for idx, row in enumerate(weight_rows):
                person_id = int(contribution_member_ids[idx])
                choice = simulate_member_portfolio_preference(
                    member_id=person_id,
                    years_to_retirement=float(contribution_years_to_retirement[idx]),
                    funded_ratio=funded_ratio,
                    stress_pass_rate=stress_pass_rate,
                    event_pressure=current_pressure,
                    seed=cfg.seed,
                    year=year,
                )
                tallies[choice] += int(row.published_weight)
                counts[choice] += 1
                if row.wallet in top_weight_wallets:
                    preference_rows.append(
                        {
                            "member_label": f"Sim member {person_id}",
                            "window_contribution": round(float(row.window_contribution), 2),
                            "normalized_contribution": round(float(row.normalized_contribution), 4),
                            "published_weight": int(row.published_weight),
                            "vote_share_pct": round(float(row.vote_share) * 100.0, 3),
                            "preference": choice.replace("_", " ").title(),
                            "years_to_retirement": round(float(contribution_years_to_retirement[idx]), 1),
                        }
                    )
            ranked = sorted(
                portfolio_order(),
                key=lambda key: (-tallies[key], portfolio_order().index(key)),
            )
            winner_key = ranked[0]
            validation_map = {key: validate_simulated_policy(key, validation_inputs) for key in portfolio_order()}
            winner_validation = validation_map[winner_key]
            adopted_key = winner_key if winner_validation.passes else active_policy_key
            ballot_status = "Adopted" if winner_validation.passes else "Blocked"
            policy_next_year = adopted_key

            investment_ballot_rows.append(
                {
                    "year": year,
                    "round_name": f"policy-round-{year}",
                    "electorate_size": int(contribution_member_ids.size),
                    "total_window_contributions": round(float(contribution_total), 2),
                    "winning_policy": winner_key,
                    "winning_policy_name": MODEL_PORTFOLIOS[winner_key].name,
                    "winning_support_pct": round(tallies[winner_key] * 100.0 / max(sum(tallies.values()), 1), 2),
                    "status": ballot_status,
                    "adopted_policy": adopted_key,
                    "adopted_policy_name": MODEL_PORTFOLIOS[adopted_key].name,
                    "blocked_reason": "" if winner_validation.passes else winner_validation.reason,
                    "passing_policy_count": int(sum(1 for result in validation_map.values() if result.passes)),
                    "fallback_rule": "Keep previous policy active when the winner fails guardrails.",
                }
            )
            investment_vote_snapshot_rows.extend(
                [
                    {
                        "year": year,
                        "row_type": "portfolio_support",
                        "portfolio_key": key,
                        "portfolio_name": MODEL_PORTFOLIOS[key].name,
                        "weighted_votes": int(tallies[key]),
                        "support_share_pct": round(tallies[key] * 100.0 / max(sum(tallies.values()), 1), 2),
                        "voter_count": int(counts[key]),
                        "is_winner": "yes" if key == winner_key else "no",
                        "guardrail_status": "Passes" if validation_map[key].passes else "Blocked",
                        "reason": validation_map[key].reason,
                    }
                    for key in portfolio_order()
                ]
            )
            investment_vote_snapshot_rows.extend(
                [
                    {
                        "year": year,
                        "row_type": "voter_sample",
                        "portfolio_key": "sample",
                        "portfolio_name": row["member_label"],
                        "weighted_votes": int(row["published_weight"]),
                        "support_share_pct": float(row["vote_share_pct"]),
                        "voter_count": int(round(row["years_to_retirement"])),
                        "is_winner": row["preference"],
                        "guardrail_status": "Sample weight",
                        "reason": (
                            f"Contributed £{row['window_contribution']:,.0f} in the window and received "
                            f"{row['vote_share_pct']:.2f}% published weight."
                        ),
                    }
                    for row in preference_rows[:12]
                ]
            )
            investment_policy_rows.append(
                {
                    "year": year,
                    "policy_key": active_policy_key,
                    "policy_name": MODEL_PORTFOLIOS[active_policy_key].name,
                    "status": "Active this year",
                    "effective_year": year,
                    "reason": "Policy used to drive this year's return and inflation sensitivity.",
                }
            )
            investment_policy_rows.append(
                {
                    "year": year + 1,
                    "policy_key": adopted_key,
                    "policy_name": MODEL_PORTFOLIOS[adopted_key].name,
                    "status": "Adopted next year" if winner_validation.passes else "Previous policy stays active",
                    "effective_year": year + 1,
                    "reason": (
                        f"Members selected {MODEL_PORTFOLIOS[winner_key].name} and it passed guardrails."
                        if winner_validation.passes
                        else (
                            f"Members selected {MODEL_PORTFOLIOS[winner_key].name}, but it was blocked. "
                            "The previous policy remains active next year."
                        )
                    ),
                }
            )

            finalize_detail = (
                f"The ballot winner was {MODEL_PORTFOLIOS[winner_key].name}. "
                f"{winner_validation.reason}"
            )
            event_rows.append(
                {
                    "year": year,
                    "lane": "Governance",
                    "label": "Investment ballot finalized",
                    "detail": finalize_detail,
                    "severity": "good" if winner_validation.passes else "warn",
                    "contract": "InvestmentPolicyBallot",
                    "action": "finalizeBallot",
                    "classification": "proposed" if winner_validation.passes else "advisory",
                }
            )
            event_rows.append(
                {
                    "year": year,
                    "lane": "Governance",
                    "label": "Investment policy adopted" if winner_validation.passes else "Investment policy blocked",
                    "detail": (
                        f"{MODEL_PORTFOLIOS[adopted_key].name} will guide the next simulation years."
                        if winner_validation.passes
                        else (
                            f"{MODEL_PORTFOLIOS[winner_key].name} won the vote but failed the fairness / risk guardrails. "
                            f"{MODEL_PORTFOLIOS[active_policy_key].name} stays active."
                        )
                    ),
                    "severity": "good" if winner_validation.passes else "bad",
                    "contract": "InvestmentPolicyBallot",
                    "action": "finalizeBallot",
                    "classification": "executable" if winner_validation.passes else "advisory",
                }
            )
            investment_onchain_rows.extend(
                [
                    {
                        "year": year,
                        "simulation": "Investment ballot opened",
                        "contract": "InvestmentPolicyBallot",
                        "action": "createBallot",
                        "classification": "proposed",
                        "detail": (
                            f"Would publish ballot policy-round-{year} with model portfolios "
                            f"{', '.join(MODEL_PORTFOLIOS[key].name for key in portfolio_order())}."
                        ),
                    },
                    {
                        "year": year,
                        "simulation": "Investment weight snapshot prepared",
                        "contract": "InvestmentPolicyBallot",
                        "action": "setBallotWeights",
                        "classification": "proposed",
                        "detail": (
                            f"Would publish {len(weight_rows)} snapshot weights based on current-year contributor flows. "
                            "The chain stores the snapshot, not salary history."
                        ),
                    },
                    {
                        "year": year,
                        "simulation": "Investment ballot finalized",
                        "contract": "InvestmentPolicyBallot",
                        "action": "finalizeBallot",
                        "classification": "executable" if winner_validation.passes else "advisory",
                        "detail": finalize_detail,
                    },
                    {
                        "year": year,
                        "simulation": "Adopted investment policy published",
                        "contract": "InvestmentPolicyBallot",
                        "action": "finalizeBallot",
                        "classification": "executable" if winner_validation.passes else "advisory",
                        "detail": (
                            f"Would publish {MODEL_PORTFOLIOS[adopted_key].name} with allocation hash "
                            f"{allocation_hash(adopted_key)[:18]}…."
                            if winner_validation.passes
                            else "No new policy would be published because the winning ballot failed guardrails."
                        ),
                    },
                ]
            )
            onchain_rows.extend(investment_onchain_rows[-4:])
            if winner_validation.passes:
                pending_policy_key = adopted_key
                pending_effective_year = year + 1
        elif _ballot_due(cfg, year_offset):
            investment_ballot_rows.append(
                {
                    "year": year,
                    "round_name": f"policy-round-{year}",
                    "electorate_size": int(contribution_member_ids.size),
                    "total_window_contributions": round(float(contribution_total), 2),
                    "winning_policy": "",
                    "winning_policy_name": "No valid ballot",
                    "winning_support_pct": 0.0,
                    "status": "Not opened",
                    "adopted_policy": active_policy_key,
                    "adopted_policy_name": MODEL_PORTFOLIOS[active_policy_key].name,
                    "blocked_reason": "Too few active contributors remained to satisfy the strict 5% vote-share cap.",
                    "passing_policy_count": 0,
                    "fallback_rule": "No ballot was opened; the previous policy stayed active.",
                }
            )
            event_rows.append(
                {
                    "year": year,
                    "lane": "Governance",
                    "label": "Investment ballot blocked",
                    "detail": (
                        "The Twin did not open a ballot because too few active contributors remained to satisfy the strict 5% vote-share cap."
                    ),
                    "severity": "warn",
                    "contract": "InvestmentPolicyBallot",
                    "action": "createBallot",
                    "classification": "advisory",
                }
            )

        investment_policy_rows.append(
            {
                "year": year,
                "policy_key": active_policy_key,
                "policy_name": MODEL_PORTFOLIOS[active_policy_key].name,
                "status": "Active policy",
                "effective_year": year,
                "reason": "Policy used for this simulation year.",
            }
        )
        annual_rows[-1].update(
            {
                "event_pressure": round(current_pressure, 4),
                "active_policy": active_policy_key,
                "active_policy_name": MODEL_PORTFOLIOS[active_policy_key].name,
                "policy_next_year": policy_next_year,
                "policy_next_year_name": MODEL_PORTFOLIOS[policy_next_year].name,
                "investment_ballot_status": ballot_status,
                "policy_expected_return": round(MODEL_PORTFOLIOS[active_policy_key].expected_return, 4),
                "policy_expected_return_pct": round(MODEL_PORTFOLIOS[active_policy_key].expected_return * 100.0, 2),
                "policy_inflation_hedge": round(MODEL_PORTFOLIOS[active_policy_key].inflation_hedge, 4),
                "policy_inflation_hedge_pct": round(MODEL_PORTFOLIOS[active_policy_key].inflation_hedge * 100.0, 2),
                "policy_stress_drawdown": round(MODEL_PORTFOLIOS[active_policy_key].stress_drawdown, 4),
                "policy_stress_drawdown_pct": round(MODEL_PORTFOLIOS[active_policy_key].stress_drawdown * 100.0, 2),
                "policy_fairness_pressure": round(MODEL_PORTFOLIOS[active_policy_key].fairness_pressure, 4),
                "policy_fairness_pressure_pct": round(MODEL_PORTFOLIOS[active_policy_key].fairness_pressure * 100.0, 2),
            }
        )
        previous_pressure = current_pressure

    annual_df = pd.DataFrame(annual_rows)
    cohort_df_all = pd.DataFrame(cohort_rows)
    persona_df = pd.DataFrame(persona_rows)
    event_df = pd.DataFrame(event_rows)
    proposal_df = pd.DataFrame(proposal_rows)
    onchain_df = pd.DataFrame(onchain_rows)
    mortality_history_df = pd.DataFrame(mortality_rows)
    mortality_basis_df = pd.DataFrame(mortality_basis_rows)
    investment_ballot_df = pd.DataFrame(investment_ballot_rows)
    investment_policy_df = pd.DataFrame(investment_policy_rows)
    investment_vote_snapshot_df = pd.DataFrame(investment_vote_snapshot_rows)
    investment_onchain_df = pd.DataFrame(investment_onchain_rows)

    if not investment_ballot_df.empty and not annual_df.empty:
        for row in investment_ballot_df.to_dict("records"):
            ballot_year = int(row["year"])
            after_window = annual_df.loc[annual_df["year"] >= ballot_year + 1].head(2)
            if after_window.empty:
                continue
            before_row = annual_df.loc[annual_df["year"] == ballot_year].iloc[0]
            after_row = after_window.iloc[-1]
            investment_effect_rows.append(
                {
                    "ballot_year": ballot_year,
                    "winning_policy_name": str(row["winning_policy_name"]),
                    "adopted_policy_name": str(row["adopted_policy_name"]),
                    "status": str(row["status"]),
                    "before_nav_m": round(float(before_row["fund_nav"]) / 1_000_000, 3),
                    "after_nav_m": round(float(after_row["fund_nav"]) / 1_000_000, 3),
                    "funded_ratio_change_pct": round((float(after_row["funded_ratio"]) - float(before_row["funded_ratio"])) * 100.0, 2),
                    "gini_change_pct": round((float(after_row["gini"]) - float(before_row["gini"])) * 100.0, 2),
                    "stress_pass_change_pct": round((float(after_row["stress_pass_rate"]) - float(before_row["stress_pass_rate"])) * 100.0, 2),
                    "summary": (
                        f"After the {ballot_year} ballot, assets moved from £{float(before_row['fund_nav'])/1_000_000:.1f}m "
                        f"to £{float(after_row['fund_nav'])/1_000_000:.1f}m while funded ratio moved by "
                        f"{(float(after_row['funded_ratio']) - float(before_row['funded_ratio']))*100.0:+.1f} pts."
                    ),
                }
            )
    investment_effect_df = pd.DataFrame(investment_effect_rows)
    investment_summary = {
        "enabled": bool(cfg.investment_voting_enabled),
        "ballot_count": int(len(investment_ballot_df)),
        "adopted_count": int((investment_ballot_df["status"] == "Adopted").sum()) if not investment_ballot_df.empty else 0,
        "blocked_count": int((investment_ballot_df["status"] == "Blocked").sum()) if not investment_ballot_df.empty else 0,
        "latest_policy_key": str(annual_df.iloc[-1]["active_policy"]) if not annual_df.empty else active_policy_key,
        "latest_policy_name": MODEL_PORTFOLIOS[str(annual_df.iloc[-1]["active_policy"])].name if not annual_df.empty else MODEL_PORTFOLIOS[active_policy_key].name,
        "ballot_years": [int(row["year"]) for row in investment_ballot_df.to_dict("records")] if not investment_ballot_df.empty else [],
        "summary_text": (
            "Member investment ballots were disabled in this run."
            if not cfg.investment_voting_enabled
            else (
                f"{len(investment_ballot_df)} ballot(s) were simulated in years "
                f"{', '.join(str(int(y)) for y in investment_ballot_df['year'].tolist())}. "
                f"{int((investment_ballot_df['status'] == 'Adopted').sum()) if not investment_ballot_df.empty else 0} policy decision(s) passed guardrails, "
                f"and {int((investment_ballot_df['status'] == 'Blocked').sum()) if not investment_ballot_df.empty else 0} winning ballot(s) were blocked, leaving the previous policy in place."
                if not investment_ballot_df.empty
                else "No investment ballot was simulated in this run."
            )
        ),
    }
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
        "PIUs are non-transferable active-pool accumulation units. Contributions buy PIUs at the published price, and the price is a smoothed NAV-per-active-PIU measure.",
        "Fairness and stress are evaluated at cohort level using aggregate contribution and indexed entitlement estimates.",
        "Mortality starts from a baseline Gompertz-Makeham prior and then blends toward fund experience through a cohort-level credibility weight.",
        "Only mortality-basis snapshots, cohort multipliers, and study hashes belong on chain; raw death records and private member data stay off chain.",
        "Inflation shocks can persist across years and create benefit/funding pressure, but CPI is no longer the primary PIU price driver.",
        "CohortLedger.setPiuPrice publishes the smoothed PIU price; CohortLedger.contribute mints PIUs; VestaRouter.openRetirement burns or locks PIUs and opens the pension stream.",
        "Backstop releases occur when benefit payments exceed member balances and reserve support is needed.",
        "When investment voting is enabled, only active contributors in that simulation year can vote. Each receives one base vote plus a capped concave boost from current-period contribution flow.",
        "If the winning portfolio fails the fairness / risk guardrails, the Twin keeps the previous policy active rather than forcing a fallback portfolio through.",
        "The blockchain role for investment governance is ballot publication, weight-snapshot publication, and final policy publication. No direct trading logic is placed on chain.",
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
        investment_ballots=investment_ballot_df,
        investment_policy_history=investment_policy_df,
        investment_vote_snapshot=investment_vote_snapshot_df,
        investment_summary=investment_summary,
        investment_effects=investment_effect_df,
        investment_onchain=investment_onchain_df,
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
