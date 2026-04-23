"""Representative persona selection for Digital Twin V2."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from engine.population_v2 import STATUS_ACTIVE, STATUS_RETIRED, SyntheticPopulation


@dataclass(frozen=True)
class PersonaSpec:
    key: str
    label: str
    description: str


PERSONA_SPECS: tuple[PersonaSpec, ...] = (
    PersonaSpec("young", "Young starter", "Newly established worker with decades to retirement."),
    PersonaSpec("mid", "Mid-career builder", "Steady contributor in the thick of accumulation."),
    PersonaSpec("near", "Near retirement", "Older active member approaching decumulation."),
    PersonaSpec("retiree", "Retired pensioner", "Existing pensioner drawing indexed benefits."),
)


def pick_representative_indices(pop: SyntheticPopulation, year: int) -> dict[str, int]:
    """Choose stable representative personas from the current society."""
    if pop.size() == 0:
        return {}
    ages = pop.ages(year)
    alive = pop.status != 2
    active = alive & (pop.status == STATUS_ACTIVE)
    retired = alive & (pop.status == STATUS_RETIRED)

    picks: dict[str, int] = {}
    if active.any():
        active_idx = np.where(active)[0]
        active_ages = ages[active]
        picks["young"] = int(active_idx[np.argmin(active_ages)])
        median_age = np.median(active_ages)
        picks["mid"] = int(active_idx[np.argmin(np.abs(active_ages - median_age))])
        years_to_retire = pop.retirement_age[active] - active_ages
        picks["near"] = int(active_idx[np.argmin(np.abs(years_to_retire))])
    if retired.any():
        retired_idx = np.where(retired)[0]
        retired_balances = pop.balance[retired]
        picks["retiree"] = int(retired_idx[np.argmax(retired_balances)])

    # If a bucket is missing, fall back to the first alive member.
    fallback = int(np.where(alive)[0][0])
    for spec in PERSONA_SPECS:
        picks.setdefault(spec.key, fallback)
    return picks


def persona_catalog() -> list[dict[str, str]]:
    return [
        {"key": spec.key, "label": spec.label, "description": spec.description}
        for spec in PERSONA_SPECS
    ]


__all__ = ["PERSONA_SPECS", "PersonaSpec", "persona_catalog", "pick_representative_indices"]
