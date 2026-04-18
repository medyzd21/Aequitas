"""Fairness metrics for Aequitas.

Keeps the Phase-1 `fairness_corridor_check` unchanged (same signature, same
return keys) and adds richer intergenerational-fairness helpers that work
off per-cohort Money's Worth Ratios (MWRs) and EPVs.

Definitions used here:
    MWR_c   = EPV_benefits_c / EPV_contributions_c   (cohort c)
    A scheme is "fair" when MWRs across cohorts are close — any cohort
    getting systematically more or less than their contributions bought is
    an intergenerational transfer.

Metrics:
    fairness_corridor_check     pairwise EPV-change test (original MVP)
    mwr_dispersion              standard deviation / range of MWR
    mwr_gini                    Gini coefficient of MWRs
    intergenerational_index     1 − (max|MWR_c − 1|) clipped to [0, 1]
    evaluate_proposal           apply a Proposal and return before/after
"""
from __future__ import annotations

from typing import Iterable, Mapping

import math


# ---------------------------------------------------------------------------
# Phase-1 — unchanged signature
# ---------------------------------------------------------------------------

def fairness_corridor_check(
    cohort_epvs_old: dict,
    cohort_epvs_new: dict,
    epv_benchmark: float,
    delta: float = 0.05,
):
    """Original pairwise corridor check from the MVP.

    A proposed change is "fair" if, across every pair of cohorts (i, j), the
    *difference in EPV change* is at most `delta` × `epv_benchmark`.
    """
    cohorts = list(cohort_epvs_old.keys())
    max_dev = 0.0
    worst_pair = None
    for i in cohorts:
        for j in cohorts:
            delta_i = cohort_epvs_new[i] - cohort_epvs_old[i]
            delta_j = cohort_epvs_new[j] - cohort_epvs_old[j]
            dev = abs(delta_i - delta_j) / epv_benchmark if epv_benchmark else 0.0
            if dev > max_dev:
                max_dev = dev
                worst_pair = (i, j)
    return {
        "passes": max_dev <= delta,
        "max_deviation": max_dev,
        "delta_limit": delta,
        "worst_pair": worst_pair,
    }


# ---------------------------------------------------------------------------
# New metrics
# ---------------------------------------------------------------------------

def mwr_dispersion(mwrs: Mapping[int, float]) -> dict[str, float]:
    """Summary stats of MWRs across cohorts."""
    vals = [float(v) for v in mwrs.values() if v is not None]
    if not vals:
        return {"min": 0.0, "max": 0.0, "mean": 0.0, "std": 0.0, "range": 0.0}
    mean = sum(vals) / len(vals)
    var = sum((v - mean) ** 2 for v in vals) / len(vals)
    return {
        "min": min(vals),
        "max": max(vals),
        "mean": mean,
        "std": math.sqrt(var),
        "range": max(vals) - min(vals),
    }


def mwr_gini(mwrs: Mapping[int, float]) -> float:
    """Gini coefficient of a list of MWRs, in [0, 1].

    0 means every cohort gets the same deal, 1 means all benefit goes to a
    single cohort. Computed from absolute pairwise differences.
    """
    vals = sorted(float(v) for v in mwrs.values() if v is not None)
    n = len(vals)
    if n == 0 or all(v == 0 for v in vals):
        return 0.0
    total = sum(vals)
    cum = sum((2 * i - n - 1) * v for i, v in enumerate(vals, start=1))
    return abs(cum) / (n * total)


def intergenerational_index(mwrs: Mapping[int, float]) -> float:
    """A 0..1 score. 1 = every cohort gets MWR = 1. 0 = worst cohort is
    ≥100% off actuarial parity. Useful as a single governance KPI."""
    vals = [float(v) for v in mwrs.values() if v is not None]
    if not vals:
        return 0.0
    worst = max(abs(v - 1.0) for v in vals)
    return max(0.0, 1.0 - worst)


def evaluate_proposal(
    cohort_valuation: Mapping[int, Mapping[str, float]],
    proposal_multipliers: Mapping[int, float],
    delta: float = 0.05,
) -> dict:
    """Apply cohort-level benefit multipliers and re-check fairness.

    `cohort_valuation` is the output of CohortLedger.cohort_valuation():
        {cohort: {epv_contributions, epv_benefits, money_worth_ratio, members}}
    Returns before/after metrics and a pass/fail flag.
    """
    cohorts = sorted(cohort_valuation.keys())
    if not cohorts:
        return {"passes": True, "note": "no cohorts"}

    epv_old = {c: cohort_valuation[c]["epv_benefits"] for c in cohorts}
    epv_contribs = {c: cohort_valuation[c]["epv_contributions"] for c in cohorts}

    epv_new = {c: epv_old[c] * float(proposal_multipliers.get(c, 1.0)) for c in cohorts}

    # MWRs before/after
    mwr_old = {c: (epv_old[c] / epv_contribs[c]) if epv_contribs[c] else 0.0 for c in cohorts}
    mwr_new = {c: (epv_new[c] / epv_contribs[c]) if epv_contribs[c] else 0.0 for c in cohorts}

    benchmark = sum(epv_old.values()) / max(1, len(cohorts))
    corridor = fairness_corridor_check(epv_old, epv_new, benchmark, delta=delta)

    return {
        "passes": corridor["passes"],
        "corridor": corridor,
        "mwr_before": mwr_old,
        "mwr_after": mwr_new,
        "dispersion_before": mwr_dispersion(mwr_old),
        "dispersion_after": mwr_dispersion(mwr_new),
        "gini_before": mwr_gini(mwr_old),
        "gini_after": mwr_gini(mwr_new),
        "index_before": intergenerational_index(mwr_old),
        "index_after": intergenerational_index(mwr_new),
    }
