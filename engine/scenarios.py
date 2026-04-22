"""Scenario presets for the Aequitas digital-twin simulator.

Each preset is a fully-populated `SystemConfig` — the simulator takes
one and runs it. Keeping presets here (instead of inside
`system_simulation`) lets the UI expose a dropdown without importing
simulator internals, and lets tests pick a small preset cheaply.

All scenarios share the same timestep (one year) and the same actuarial
engine — they differ only in the economic / demographic narrative.

Beginner notes
--------------
* "stable" is the baseline — no shocks, modest growth. Everything else
  is derived from stable by perturbing one or two knobs.
* "market_crash" triggers a one-time 25% fund drop in year ~6.
* "inflation_shock" spikes inflation in one year, forcing benefit
  indexation.
* "aging_society" lowers joiner rate and raises life expectancy
  (mortality multiplier < 1).
* "unfair_reform" schedules a proposal that cuts the youngest cohort
  by 4% in year 4.
* "young_stress" loads β heavily toward younger cohorts so the
  stochastic shock concentrates on them.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from engine.population import PopulationConfig, EntrantConfig


# ---------------------------------------------------------------------------
# One-off event schedule — lets scenarios pre-declare shocks / proposals
# ---------------------------------------------------------------------------

@dataclass
class ScheduledShock:
    """A one-off event scheduled at a specific simulation year (offset)."""
    offset: int                      # 0-indexed year within the sim horizon
    kind: str                        # one of engine.events.*
    magnitude: float = 0.0           # shock strength (drop fraction, multiplier, etc.)
    note: str = ""


@dataclass
class ScheduledProposal:
    """A governance proposal scheduled at a specific simulation year."""
    offset: int
    name: str
    # Per-cohort multiplier overrides. The simulator will fill in 1.0
    # for any cohort not mentioned.
    multipliers: dict[str, float] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# SystemConfig — the full knob-pack the simulator consumes
# ---------------------------------------------------------------------------

@dataclass
class SystemConfig:
    """End-to-end simulation configuration."""

    # run
    name:          str = "stable"
    description:   str = ""
    start_year:    int = 2026
    horizon_years: int = 40
    seed:          int = 42

    # population
    n_members:    int = 2_000
    pop_cfg:      PopulationConfig = field(default_factory=PopulationConfig)
    entrants:     EntrantConfig    = field(default_factory=EntrantConfig)

    # economy
    mean_return:       float = 0.055   # annual expected return, arithmetic
    return_vol:        float = 0.10    # annual return volatility
    salary_growth:     float = 0.02    # per-year salary growth (real)
    discount_rate:     float = 0.03    # actuarial discount (EPV)
    inflation:         float = 0.02    # used for benefit indexation

    # demographics
    mortality_multiplier: float = 1.0  # 1.0 = baseline Gompertz-Makeham
    retirement_fraction:  float = 1.0  # 1.0 = everyone retires exactly at retirement_age

    # governance + stress
    stress_every_years: int = 5        # run stochastic stress every N years
    stress_scenarios:   int = 800      # scenarios per stress run (kept modest)
    corridor_delta:     float = 0.05   # fairness corridor δ

    # backstop
    backstop_initial:     float = 0.0  # £ in the reserve at year 0
    backstop_deposit_bps: int  = 25    # fraction (bps) of annual contributions auto-sent to backstop
    backstop_release_threshold: float = 0.40  # if stress_level ≥ this, release up to the shortfall

    # shocks / proposals (pre-scheduled)
    shocks:    list[ScheduledShock]    = field(default_factory=list)
    proposals: list[ScheduledProposal] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Presets
# ---------------------------------------------------------------------------

def stable() -> SystemConfig:
    """Baseline: modest growth, no shocks, closed-ish fund."""
    return SystemConfig(
        name="stable",
        description=(
            "Baseline economy: 5.5% mean return, 10% vol, 2% salary growth, "
            "2% inflation. No shocks, no scheduled reforms. A calm "
            "environment against which all other scenarios are compared."
        ),
        entrants=EntrantConfig(mean_per_year=30),
    )


def inflation_shock() -> SystemConfig:
    """Mid-sim inflation spike — tests benefit indexation."""
    cfg = stable()
    cfg.name = "inflation_shock"
    cfg.description = (
        "A mid-horizon inflation spike hits the scheme. The stochastic "
        "stress run picks up the dispersion it introduces across cohorts."
    )
    cfg.shocks = [
        ScheduledShock(offset=8, kind="inflation_shock",
                       magnitude=0.11, note="11% inflation for one year"),
        ScheduledShock(offset=9, kind="inflation_shock",
                       magnitude=0.07, note="tail-off 7%"),
    ]
    return cfg


def market_crash() -> SystemConfig:
    """One-time fund NAV drop. Tests backstop release logic."""
    cfg = stable()
    cfg.name = "market_crash"
    cfg.description = (
        "A systemic 25% fund value drop in year 6, followed by slower "
        "recovery. This is where BackstopVault.release earns its keep."
    )
    cfg.backstop_initial = 500_000.0
    cfg.shocks = [
        ScheduledShock(offset=6, kind="market_crash",
                       magnitude=0.25, note="25% NAV drop"),
    ]
    cfg.return_vol = 0.13
    return cfg


def aging_society() -> SystemConfig:
    """Fewer entrants, longer lives. The hardest scheme to defend."""
    cfg = stable()
    cfg.name = "aging_society"
    cfg.description = (
        "Fewer new joiners (10/year vs 30), and longer life expectancy "
        "(mortality ×0.85). The liability side grows while the "
        "contribution side shrinks — the classic demographic squeeze."
    )
    cfg.entrants = EntrantConfig(mean_per_year=10)
    cfg.mortality_multiplier = 0.85
    return cfg


def unfair_reform() -> SystemConfig:
    """Governance scheduled a reform that cuts the youngest cohort."""
    cfg = stable()
    cfg.name = "unfair_reform"
    cfg.description = (
        "A governance proposal schedules a 4% cut on the youngest "
        "cohort in year 4 — deliberately asymmetric. The corridor "
        "check should catch it before it fires."
    )
    cfg.proposals = [
        ScheduledProposal(
            offset=4,
            name="TrimYoungest",
            multipliers={"YOUNGEST": 0.96},   # resolved inside the simulator
        ),
    ]
    return cfg


def young_stress() -> SystemConfig:
    """Heavy generational β: younger cohorts wear all the risk."""
    cfg = stable()
    cfg.name = "young_stress"
    cfg.description = (
        "Systemic β is loaded heavily toward younger cohorts: under "
        "stress, they take most of the hit. This exposes the limits "
        "of the fairness corridor under a biased economy."
    )
    cfg.return_vol = 0.12
    # the simulator's stress run already has a generational_slope knob
    # but we signal the loading here for the metadata.
    cfg.mortality_multiplier = 1.05
    return cfg


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

PRESETS: dict[str, Callable[[], SystemConfig]] = {
    "stable":          stable,
    "inflation_shock": inflation_shock,
    "market_crash":    market_crash,
    "aging_society":   aging_society,
    "unfair_reform":   unfair_reform,
    "young_stress":    young_stress,
}


def get_preset(key: str) -> SystemConfig:
    """Return a fresh copy of the named preset."""
    if key not in PRESETS:
        raise ValueError(
            f"unknown scenario {key!r}. available: {list(PRESETS)}"
        )
    return PRESETS[key]()


def list_presets() -> list[dict[str, str]]:
    """UI-friendly catalogue."""
    return [
        {"key": k, "name": fn().name, "description": fn().description}
        for k, fn in PRESETS.items()
    ]


__all__ = [
    "ScheduledShock", "ScheduledProposal",
    "SystemConfig",
    "stable", "inflation_shock", "market_crash",
    "aging_society", "unfair_reform", "young_stress",
    "PRESETS", "get_preset", "list_presets",
]
