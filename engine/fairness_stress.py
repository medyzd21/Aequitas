"""Stochastic cohort-shock fairness stress-test.

This module answers a different question from the rest of the engine.

    engine.simulation   → randomises investment returns inside the actuarial
                          model (are our deterministic investment assumptions
                          robust?).
    engine.fairness     → evaluates a SINGLE deterministic governance proposal
                          against the fairness corridor.
    engine.fairness_stress (this module)
                        → randomises cohort multipliers themselves to stand
                          in for the economic reality a cohort lived through
                          — inflation regimes, housing affordability, labour
                          precarity, policy erosion — things the actuarial
                          model ignores.

The one-factor model
--------------------
For each Monte Carlo scenario s = 1 … S, and each cohort c we draw:

    m_c^(s) = 1 + β_c · F^(s) + ε_c^(s)

where
    F^(s)      ~ Normal(0, σ_F²)   — shared macro shock per scenario.
    β_c                              — cohort exposure to that macro shock.
                                       Default: linear in birth year, so older
                                       cohorts have β > 0 (historically the
                                       "tailwind generation") and younger
                                       cohorts β < 0 ("headwind generation").
    ε_c^(s)   ~ Normal(0, σ_ε²)    — cohort-specific noise.

The multiplier scales the cohort's EPV of benefits. Applied on top of the
baseline valuation, it gives us a scenario-level MWR per cohort from which
we compute Gini, intergenerational index, and the fairness corridor.

Everything is vectorised with NumPy so 10 000 scenarios run in
milliseconds. No Pandas magic, no hidden state: call
`stochastic_cohort_stress(cohort_valuation, …)` and read the dict.

Beginner notes
--------------
* A POSITIVE macro shock F^(s) means "a history kinder to older cohorts".
  With default betas: older cohort multipliers go above 1.0, younger below.
* A NEGATIVE macro shock means the opposite.
* σ_F controls how extreme those histories can be.
* σ_ε adds per-cohort idiosyncratic variation on top.
* generational_slope controls |β|. Set it to 0 to kill the factor entirely
  and leave only idiosyncratic noise.
"""
from __future__ import annotations

from typing import Mapping

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Betas
# ---------------------------------------------------------------------------

def build_cohort_betas(
    cohorts: list[int],
    *,
    slope: float = 0.5,
    reference_year: float | None = None,
) -> dict[int, float]:
    """Return β_c for each cohort.

    Formula:   β_c = slope · (reference_year − c) / max_delta

    Older-than-reference cohorts (c < ref) → β_c positive (up to +slope).
    Younger-than-reference cohorts (c > ref) → β_c negative (down to −slope).
    Setting slope = 0 gives every cohort β_c = 0 (no factor exposure).
    """
    if not cohorts:
        return {}
    if reference_year is None:
        reference_year = sum(cohorts) / len(cohorts)
    max_delta = max(abs(c - reference_year) for c in cohorts) or 1.0
    return {c: float(slope) * (reference_year - c) / max_delta for c in cohorts}


# ---------------------------------------------------------------------------
# Core stress test
# ---------------------------------------------------------------------------

def stochastic_cohort_stress(
    cohort_valuation: Mapping[int, Mapping[str, float]],
    *,
    n_scenarios: int = 2_000,
    factor_sigma: float = 0.10,
    idiosyncratic_sigma: float = 0.03,
    betas: Mapping[int, float] | None = None,
    generational_slope: float = 0.5,
    corridor_delta: float = 0.05,
    youngest_poor_threshold: float = 0.90,
    seed: int | None = 42,
) -> dict:
    """Run the one-factor cohort-shock stress test.

    Parameters
    ----------
    cohort_valuation : dict {cohort: {epv_contributions, epv_benefits, ...}}
        Output of `CohortLedger.cohort_valuation()`.
    n_scenarios : number of Monte Carlo scenarios (columns of randomness).
    factor_sigma : σ_F — std. dev. of the shared macro factor.
    idiosyncratic_sigma : σ_ε — std. dev. of each cohort's own noise.
    betas : override per-cohort β_c; if None, built from `generational_slope`.
    generational_slope : controls how steeply β_c varies with birth year.
    corridor_delta : δ for the fairness corridor (pairwise EPV change test).
    youngest_poor_threshold : MWR level below which the youngest cohort is
        considered to have a "poor outcome" in that scenario (for the KPI).
    seed : RNG seed for reproducibility. None → fresh randomness each call.

    Returns
    -------
    dict with:
        cohorts, betas, n_scenarios, factor_sigma, idiosyncratic_sigma,
        mean_gini, p95_gini,
        mean_index, p05_index,
        corridor_pass_rate,
        worst_cohort_freq : {cohort: fraction of scenarios it was worst},
        youngest_cohort, youngest_poor_rate, youngest_poor_threshold,
        mwr_samples_df : (n_scenarios × K) DataFrame of MWRs per scenario,
        gini_series, index_series : per-scenario arrays (for distribution plots).
    """
    cohorts = sorted(cohort_valuation.keys())
    K = len(cohorts)
    if K == 0:
        return {"cohorts": [], "n_scenarios": 0, "note": "no cohorts"}

    # 1) Build betas ---------------------------------------------------------
    if betas is None:
        betas = build_cohort_betas(cohorts, slope=generational_slope)
    beta_arr = np.array([float(betas.get(c, 0.0)) for c in cohorts])

    # 2) Random draws --------------------------------------------------------
    rng = np.random.default_rng(seed)
    F = rng.normal(0.0, float(factor_sigma), size=int(n_scenarios))      # (S,)
    eps = rng.normal(0.0, float(idiosyncratic_sigma),
                     size=(int(n_scenarios), K))                          # (S, K)

    # 3) Scenario cohort multipliers  m_c^(s) = 1 + β_c F^(s) + ε_c^(s) -----
    multipliers = 1.0 + np.outer(F, beta_arr) + eps                       # (S, K)

    # 4) Apply to baseline EPVs and compute MWRs -----------------------------
    epv_c = np.array([cohort_valuation[c]["epv_contributions"] for c in cohorts])
    epv_b = np.array([cohort_valuation[c]["epv_benefits"] for c in cohorts])
    epv_b_scen = epv_b[None, :] * multipliers                             # (S, K)

    with np.errstate(divide="ignore", invalid="ignore"):
        mwr_scen = np.where(epv_c > 0, epv_b_scen / epv_c, 0.0)           # (S, K)

    # 5) Per-scenario metrics -----------------------------------------------
    gini_series = _gini_rows(mwr_scen)                                    # (S,)
    # intergen index = 1 − max_c |MWR_c − 1|, clipped to [0, 1]
    index_series = np.clip(1.0 - np.abs(mwr_scen - 1.0).max(axis=1), 0.0, 1.0)

    # Corridor pass: max pairwise |ΔEPV_i − ΔEPV_j| / benchmark ≤ δ
    # Equivalent to (max − min) of ΔEPV_c across cohorts.
    benchmark = float(epv_b.mean()) if epv_b.mean() else 1.0
    delta_b = epv_b_scen - epv_b[None, :]                                 # (S, K)
    max_dev = (delta_b.max(axis=1) - delta_b.min(axis=1)) / benchmark
    corridor_pass = max_dev <= float(corridor_delta)                      # (S,) bool

    # Worst-affected cohort per scenario = arg-min MWR across cohorts
    worst_idx = np.argmin(mwr_scen, axis=1)                               # (S,)
    worst_cohort_freq = {
        cohorts[i]: float(np.mean(worst_idx == i)) for i in range(K)
    }

    # Youngest cohort = last in the ascending sort
    youngest = cohorts[-1]
    youngest_poor_rate = float(np.mean(mwr_scen[:, -1] < float(youngest_poor_threshold)))

    # 6) Package -------------------------------------------------------------
    return {
        "cohorts": cohorts,
        "betas": dict(betas),
        "n_scenarios": int(n_scenarios),
        "factor_sigma": float(factor_sigma),
        "idiosyncratic_sigma": float(idiosyncratic_sigma),
        "corridor_delta": float(corridor_delta),
        "mean_gini": float(gini_series.mean()),
        "p95_gini": float(np.percentile(gini_series, 95)),
        "mean_index": float(index_series.mean()),
        "p05_index": float(np.percentile(index_series, 5)),
        "corridor_pass_rate": float(corridor_pass.mean()),
        "worst_cohort_freq": worst_cohort_freq,
        "youngest_cohort": int(youngest),
        "youngest_poor_threshold": float(youngest_poor_threshold),
        "youngest_poor_rate": youngest_poor_rate,
        "mwr_samples_df": pd.DataFrame(mwr_scen, columns=cohorts),
        "gini_series": gini_series,
        "index_series": index_series,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _gini_rows(mat: np.ndarray) -> np.ndarray:
    """Vectorised Gini coefficient for each row of `mat`.

    Uses the classical formula on a sorted row:
        G = |Σ_i (2i − n − 1) · v_(i)| / (n · Σv)
    """
    sorted_rows = np.sort(np.abs(mat), axis=1)
    n = sorted_rows.shape[1]
    total = sorted_rows.sum(axis=1)
    weights = 2 * np.arange(1, n + 1) - n - 1
    cum = (sorted_rows * weights).sum(axis=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        g = np.where(total > 0, np.abs(cum) / (n * total), 0.0)
    return g


def summary_frame(result: dict) -> pd.DataFrame:
    """Convert the flat KPIs into a tidy 2-column DataFrame for display."""
    if not result.get("cohorts"):
        return pd.DataFrame(columns=["metric", "value"])
    rows = [
        ("Scenarios", result["n_scenarios"]),
        ("Factor σ (macro)", result["factor_sigma"]),
        ("Idiosyncratic σ", result["idiosyncratic_sigma"]),
        ("Mean Gini (MWR)", round(result["mean_gini"], 4)),
        ("p95 Gini (worst-case)", round(result["p95_gini"], 4)),
        ("Mean intergenerational index", round(result["mean_index"], 4)),
        ("p05 intergenerational index (worst-case)", round(result["p05_index"], 4)),
        ("Corridor pass rate", f"{result['corridor_pass_rate']:.1%}"),
        (
            f"Youngest cohort ({result['youngest_cohort']}) MWR < "
            f"{result['youngest_poor_threshold']:.2f} rate",
            f"{result['youngest_poor_rate']:.1%}",
        ),
    ]
    return pd.DataFrame(rows, columns=["metric", "value"])
