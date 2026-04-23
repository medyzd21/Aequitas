"""Event process for Digital Twin V2.

Random shocks arrive during the simulation rather than being pre-baked
scenario scripts. Different event types have different arrival logic and
impact shapes: crashes are rare and heavy-tailed, inflation persists
across years, aging drifts slowly, unfair reforms appear under pressure,
and young stress disproportionately hurts younger cohorts.
"""
from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np


@dataclass(frozen=True)
class EventProcessConfig:
    enabled: bool = True
    frequency: float = 1.0
    intensity: float = 1.0
    market_crash: bool = True
    inflation_shock: bool = True
    aging_society: bool = True
    unfair_reform: bool = True
    young_stress: bool = True


@dataclass(frozen=True)
class EventProcessState:
    inflation_years_left: int = 0
    inflation_extra: float = 0.0
    aging_drift: float = 0.0
    young_stress_years_left: int = 0
    young_stress_level: float = 0.0


@dataclass(frozen=True)
class TwinShockEvent:
    year: int
    kind: str
    label: str
    detail: str
    severity: str
    contract: str
    action: str
    classification: str


def sample_year_events(
    *,
    year: int,
    rng: np.random.Generator,
    config: EventProcessConfig,
    state: EventProcessState,
    pressure: float,
) -> tuple[list[TwinShockEvent], EventProcessState, dict[str, float | bool]]:
    """Sample this year's random events and return event impacts."""
    impacts: dict[str, float | bool] = {
        "return_shock": 0.0,
        "inflation_extra": 0.0,
        "aging_drift": state.aging_drift,
        "young_stress_level": 0.0,
        "proposal_pressure": 0.0,
        "trigger_unfair_reform": False,
    }
    events: list[TwinShockEvent] = []
    next_state = state

    if state.inflation_years_left > 0:
        impacts["inflation_extra"] = state.inflation_extra
        next_state = replace(
            next_state,
            inflation_years_left=max(0, state.inflation_years_left - 1),
        )
        if next_state.inflation_years_left == 0:
            next_state = replace(next_state, inflation_extra=0.0)

    if state.young_stress_years_left > 0:
        impacts["young_stress_level"] = state.young_stress_level
        next_state = replace(
            next_state,
            young_stress_years_left=max(0, state.young_stress_years_left - 1),
        )
        if next_state.young_stress_years_left == 0:
            next_state = replace(next_state, young_stress_level=0.0)

    if not config.enabled:
        if config.aging_society:
            drift = min(0.30, next_state.aging_drift + 0.0012 * config.intensity)
            next_state = replace(next_state, aging_drift=drift)
            impacts["aging_drift"] = drift
        return events, next_state, impacts

    freq = max(0.05, float(config.frequency))
    intensity = max(0.05, float(config.intensity))

    if config.market_crash and rng.poisson(0.045 * freq) > 0:
        drop = float(min(0.48, 0.07 + rng.pareto(2.8) * 0.08 * intensity + rng.uniform(0.04, 0.10)))
        impacts["return_shock"] = -drop
        impacts["proposal_pressure"] = max(float(impacts["proposal_pressure"]), drop)
        events.append(
            TwinShockEvent(
                year=year,
                kind="market_crash",
                label="Market crash",
                detail=f"Rare heavy-tail shock cut investment performance by about {drop:.0%} this year.",
                severity="bad",
                contract="StressOracle",
                action="updateStressLevel",
                classification="advisory",
            )
        )

    if config.inflation_shock and next_state.inflation_years_left == 0 and rng.poisson(0.08 * freq) > 0:
        duration = int(rng.integers(2, 5))
        extra = float(min(0.09, 0.018 + rng.uniform(0.01, 0.05) * intensity))
        next_state = replace(next_state, inflation_years_left=duration - 1, inflation_extra=extra)
        impacts["inflation_extra"] = extra
        impacts["proposal_pressure"] = max(float(impacts["proposal_pressure"]), extra * 3.0)
        events.append(
            TwinShockEvent(
                year=year,
                kind="inflation_shock",
                label="Inflation regime",
                detail=f"Persistent inflation regime started and is expected to last about {duration} years, which means PIU price updates will become more demanding.",
                severity="warn",
                contract="CohortLedger",
                action="setPiuPrice",
                classification="executable",
            )
        )

    if config.aging_society:
        drift_step = float(0.0010 + rng.uniform(0.0003, 0.0020) * intensity)
        drift = min(0.32, next_state.aging_drift + drift_step)
        next_state = replace(next_state, aging_drift=drift)
        impacts["aging_drift"] = drift
        if year % 5 == 0 or rng.poisson(0.18 * freq) > 0:
            events.append(
                TwinShockEvent(
                    year=year,
                    kind="aging_society",
                    label="Aging drift",
                    detail="Structural aging pressure continued: fewer entrants and longer-lived retirees are reshaping the fund.",
                    severity="warn",
                    contract="StressOracle",
                    action="updateStressLevel",
                    classification="advisory",
                )
            )

    if config.young_stress and next_state.young_stress_years_left == 0 and rng.poisson(0.06 * freq) > 0:
        duration = int(rng.integers(2, 5))
        level = float(min(1.0, 0.25 + rng.uniform(0.10, 0.45) * intensity))
        next_state = replace(next_state, young_stress_years_left=duration - 1, young_stress_level=level)
        impacts["young_stress_level"] = level
        impacts["proposal_pressure"] = max(float(impacts["proposal_pressure"]), level * 0.6)
        events.append(
            TwinShockEvent(
                year=year,
                kind="young_stress",
                label="Young-cohort stress",
                detail="A systemic stress regime hit younger workers harder than older cohorts, increasing fairness pressure.",
                severity="warn",
                contract="StressOracle",
                action="updateStressLevel",
                classification="advisory",
            )
        )

    reform_pressure = float(np.clip(pressure + float(impacts["proposal_pressure"]), 0.0, 1.5))
    unfair_rate = max(0.0, (reform_pressure - 0.25) * 0.35 * freq)
    if config.unfair_reform and unfair_rate > 0 and rng.poisson(unfair_rate) > 0:
        impacts["trigger_unfair_reform"] = True
        events.append(
            TwinShockEvent(
                year=year,
                kind="unfair_reform",
                label="Pressure-driven reform proposal",
                detail="Fiscal and fairness pressure triggered a governance proposal for review.",
                severity="bad",
                contract="FairnessGate",
                action="submitAndEvaluate",
                classification="proposed",
            )
        )

    return events, next_state, impacts


__all__ = [
    "EventProcessConfig",
    "EventProcessState",
    "TwinShockEvent",
    "sample_year_events",
]
