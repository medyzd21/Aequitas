"""Member-governed investment policy for Aequitas.

This module is the economic source of truth for the investment-ballot MVP.
It keeps the portfolio menu, voting-weight rule, and publication guardrails
off-chain in Python, then hands only the compact execution surface to the
Solidity layer.

Design boundaries
-----------------
* Members vote on predefined model portfolios, not arbitrary asset weights.
* Voting power is based on the current contribution window, not lifetime wealth.
* Every eligible member gets a base vote.
* Contributions add only a modest concave boost: ``1 + sqrt(normalized_window)``.
* Any single member's published share is capped at 5%.
* The guardrail validator is intentionally practical rather than pretending to
  be a full strategic-asset-allocation optimizer. It uses the scheme's current
  funding, fairness, and stress posture plus declared portfolio assumptions to
  decide whether the winning policy is publishable.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from typing import Iterable, Mapping, Sequence

from engine.fairness import intergenerational_index, mwr_gini
from engine.ledger import CohortLedger
from engine.models import Member


ASSET_UNIVERSE: tuple[str, ...] = (
    "global_equity",
    "developed_sovereign_bonds",
    "inflation_linked_bonds",
    "gold",
    "cash_reserve",
)
MAX_EFFECTIVE_SHARE = 0.05
DEFAULT_WEIGHT_SCALE = 1_000_000
MIN_VOTERS_FOR_STRICT_CAP = math.ceil(1.0 / MAX_EFFECTIVE_SHARE)


@dataclass(frozen=True)
class ModelPortfolio:
    key: str
    name: str
    description: str
    allocation: Mapping[str, int]
    expected_return: float
    stress_drawdown: float
    inflation_hedge: float
    fairness_pressure: float


@dataclass(frozen=True)
class VoteSnapshotRow:
    wallet: str
    window_contribution: float
    normalized_contribution: float
    raw_score: float
    vote_share: float
    published_weight: int


@dataclass(frozen=True)
class SimulationPolicyValidationInputs:
    funded_ratio_before: float
    gini_before: float
    intergen_before: float
    stress_pass_rate_before: float
    expected_inflation: float
    retiree_share: float
    near_retire_share: float


@dataclass(frozen=True)
class PolicyValidationResult:
    portfolio_key: str
    passes: bool
    reason: str
    funded_ratio_before: float
    funded_ratio_after: float
    funded_ratio_deterioration: float
    gini_before: float
    gini_after: float
    gini_worsening: float
    stress_pass_rate: float
    intergen_before: float
    intergen_after: float


@dataclass(frozen=True)
class BallotDraft:
    round_name: str
    opens_at: int
    closes_at: int
    portfolio_order: tuple[str, ...]
    weight_rows: tuple[VoteSnapshotRow, ...]
    support_rows: tuple[dict[str, object], ...]
    winner_key: str
    winner_validation: PolicyValidationResult
    validation_by_portfolio: Mapping[str, PolicyValidationResult]


MODEL_PORTFOLIOS: dict[str, ModelPortfolio] = {
    "growth": ModelPortfolio(
        key="growth",
        name="Growth",
        description="More growth-seeking: stronger global equity tilt and a lighter bond cushion.",
        allocation={
            "global_equity": 70,
            "developed_sovereign_bonds": 10,
            "inflation_linked_bonds": 10,
            "gold": 5,
            "cash_reserve": 5,
        },
        expected_return=0.061,
        stress_drawdown=0.23,
        inflation_hedge=0.32,
        fairness_pressure=0.070,
    ),
    "balanced": ModelPortfolio(
        key="balanced",
        name="Balanced",
        description="Middle path: diversified risk with explicit inflation-linked protection.",
        allocation={
            "global_equity": 50,
            "developed_sovereign_bonds": 20,
            "inflation_linked_bonds": 15,
            "gold": 10,
            "cash_reserve": 5,
        },
        expected_return=0.050,
        stress_drawdown=0.14,
        inflation_hedge=0.48,
        fairness_pressure=0.035,
    ),
    "defensive": ModelPortfolio(
        key="defensive",
        name="Defensive",
        description="More stability-focused: lower equity exposure and more liability-matching ballast.",
        allocation={
            "global_equity": 30,
            "developed_sovereign_bonds": 35,
            "inflation_linked_bonds": 20,
            "gold": 10,
            "cash_reserve": 5,
        },
        expected_return=0.041,
        stress_drawdown=0.08,
        inflation_hedge=0.61,
        fairness_pressure=0.020,
    ),
}


def validate_allocation(allocation: Mapping[str, int | float]) -> None:
    """Ensure a model portfolio is well-formed and sums to 100."""
    missing = [asset for asset in ASSET_UNIVERSE if asset not in allocation]
    extras = [asset for asset in allocation if asset not in ASSET_UNIVERSE]
    if missing or extras:
        raise ValueError(
            "allocation must use the declared asset universe exactly; "
            f"missing={missing}, extras={extras}"
        )
    total = sum(float(allocation[asset]) for asset in ASSET_UNIVERSE)
    if abs(total - 100.0) > 1e-9:
        raise ValueError(f"allocation must sum to 100, got {total:.6f}")


for _portfolio in MODEL_PORTFOLIOS.values():
    validate_allocation(_portfolio.allocation)


def portfolio_catalog() -> list[dict[str, object]]:
    """Product-facing portfolio metadata."""
    rows: list[dict[str, object]] = []
    for portfolio in MODEL_PORTFOLIOS.values():
        rows.append(
            {
                "key": portfolio.key,
                "name": portfolio.name,
                "description": portfolio.description,
                "allocation": {asset: int(portfolio.allocation[asset]) for asset in ASSET_UNIVERSE},
                "allocation_hash": allocation_hash(portfolio.key),
            }
        )
    return rows


def allocation_hash(portfolio_key: str) -> str:
    """Hash a canonical allocation payload into a bytes32-shaped hex string."""
    portfolio = MODEL_PORTFOLIOS[portfolio_key]
    canonical = json.dumps(
        {asset: int(portfolio.allocation[asset]) for asset in ASSET_UNIVERSE},
        sort_keys=True,
        separators=(",", ":"),
    )
    return "0x" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def portfolio_order() -> list[str]:
    return list(MODEL_PORTFOLIOS.keys())


def decision_window_contributions(
    members: Sequence[Member],
    *,
    window_fraction: float = 1.0,
) -> dict[str, float]:
    """Estimate current-window contribution power for the ballot snapshot.

    The ledger does not yet store a dedicated decision-window contribution
    history. For the MVP, the snapshot uses each member's current annualised
    contribution flow ``salary * contribution_rate * window_fraction``.
    Inactive members still keep their base vote but receive no contribution
    boost in the current window.
    """
    fraction = max(0.0, float(window_fraction))
    out: dict[str, float] = {}
    for member in members:
        annual_flow = float(member.salary) * float(member.contribution_rate) if member.active else 0.0
        out[str(member.wallet)] = max(0.0, annual_flow * fraction)
    return out


def _capped_shares(raw_scores: Sequence[float], max_share: float) -> list[float]:
    if not raw_scores:
        return []
    if len(raw_scores) < math.ceil(1.0 / max_share):
        raise ValueError(
            f"A strict {max_share:.0%} vote-share cap requires at least "
            f"{math.ceil(1.0 / max_share)} eligible voters."
        )

    remaining = list(range(len(raw_scores)))
    shares = [0.0] * len(raw_scores)
    remaining_mass = 1.0

    while remaining:
        total_raw = sum(raw_scores[idx] for idx in remaining)
        if total_raw <= 0:
            equal_share = remaining_mass / len(remaining)
            for idx in remaining:
                shares[idx] = equal_share
            break

        capped_any = False
        for idx in list(remaining):
            candidate = remaining_mass * raw_scores[idx] / total_raw
            if candidate > max_share + 1e-12:
                shares[idx] = max_share
                remaining_mass -= max_share
                remaining.remove(idx)
                capped_any = True
        if not capped_any:
            total_raw = sum(raw_scores[idx] for idx in remaining)
            for idx in remaining:
                shares[idx] = remaining_mass * raw_scores[idx] / total_raw
            break
    return shares


def _quantize_shares(shares: Sequence[float], *, scale: int, max_share: float) -> list[int]:
    if not shares:
        return []
    cap_units = int(math.floor(max_share * scale + 1e-9))
    raw_units = [float(share) * scale for share in shares]
    units = [min(cap_units, int(math.floor(value))) for value in raw_units]
    remainder = int(scale - sum(units))
    if remainder < 0:
        raise ValueError("share quantization overflowed the declared cap")

    fractional_order = sorted(
        range(len(shares)),
        key=lambda idx: (raw_units[idx] - math.floor(raw_units[idx]), raw_units[idx]),
        reverse=True,
    )
    ptr = 0
    while remainder > 0 and fractional_order:
        idx = fractional_order[ptr % len(fractional_order)]
        if units[idx] < cap_units:
            units[idx] += 1
            remainder -= 1
        ptr += 1
        if ptr > len(fractional_order) * (scale + 1):
            raise ValueError("could not allocate the remaining vote units within the cap")
    if remainder != 0:
        raise ValueError("share quantization failed to hit the requested total scale")
    return units


def compute_vote_snapshot(
    members: Sequence[Member],
    *,
    max_share: float = MAX_EFFECTIVE_SHARE,
    scale: int = DEFAULT_WEIGHT_SCALE,
    window_fraction: float = 1.0,
) -> list[VoteSnapshotRow]:
    """Compute the capped concave voting snapshot for one ballot window."""
    eligible = [member for member in members if str(member.wallet)]
    contributions = decision_window_contributions(eligible, window_fraction=window_fraction)
    max_contribution = max((float(v) for v in contributions.values()), default=0.0)
    rows: list[VoteSnapshotRow] = []
    raw_scores: list[float] = []

    for member in eligible:
        wallet = str(member.wallet)
        window_contribution = float(contributions.get(wallet, 0.0))
        normalized = (
            window_contribution / max_contribution
            if max_contribution > 0
            else 0.0
        )
        raw_score = 1.0 + math.sqrt(normalized)
        raw_scores.append(raw_score)
        rows.append(
            VoteSnapshotRow(
                wallet=wallet,
                window_contribution=window_contribution,
                normalized_contribution=normalized,
                raw_score=raw_score,
                vote_share=0.0,
                published_weight=0,
            )
        )

    shares = _capped_shares(raw_scores, max_share)
    units = _quantize_shares(shares, scale=scale, max_share=max_share)
    return [
        VoteSnapshotRow(
            wallet=row.wallet,
            window_contribution=row.window_contribution,
            normalized_contribution=row.normalized_contribution,
            raw_score=row.raw_score,
            vote_share=float(share),
            published_weight=int(weight),
        )
        for row, share, weight in zip(rows, shares, units)
    ]


def compute_vote_snapshot_from_inputs(
    voter_ids: Sequence[str],
    window_contributions: Sequence[float],
    *,
    max_share: float = MAX_EFFECTIVE_SHARE,
    scale: int = DEFAULT_WEIGHT_SCALE,
) -> list[VoteSnapshotRow]:
    """Compute the same capped snapshot from Twin-simulated contributor flows."""
    voters = [str(voter_id) for voter_id in voter_ids if str(voter_id)]
    if len(voters) != len(window_contributions):
        raise ValueError("voter_ids and window_contributions must have the same length")
    max_contribution = max((max(0.0, float(v)) for v in window_contributions), default=0.0)
    rows: list[VoteSnapshotRow] = []
    raw_scores: list[float] = []
    for wallet, contribution in zip(voters, window_contributions, strict=False):
        window_contribution = max(0.0, float(contribution))
        normalized = window_contribution / max_contribution if max_contribution > 0 else 0.0
        raw_score = 1.0 + math.sqrt(normalized)
        raw_scores.append(raw_score)
        rows.append(
            VoteSnapshotRow(
                wallet=wallet,
                window_contribution=window_contribution,
                normalized_contribution=normalized,
                raw_score=raw_score,
                vote_share=0.0,
                published_weight=0,
            )
        )
    shares = _capped_shares(raw_scores, max_share)
    units = _quantize_shares(shares, scale=scale, max_share=max_share)
    return [
        VoteSnapshotRow(
            wallet=row.wallet,
            window_contribution=row.window_contribution,
            normalized_contribution=row.normalized_contribution,
            raw_score=row.raw_score,
            vote_share=float(share),
            published_weight=int(weight),
        )
        for row, share, weight in zip(rows, shares, units, strict=False)
    ]


def simulate_member_portfolio_preference(
    *,
    member_id: int,
    years_to_retirement: float,
    funded_ratio: float,
    stress_pass_rate: float,
    event_pressure: float,
    seed: int,
    year: int,
) -> str:
    """Deterministic Twin heuristic for simulated member preferences.

    Younger active contributors lean growth, mid cohorts lean balanced, and
    stressed / underfunded states pull support toward defensive. A tiny
    seed-based jitter only breaks ties; it does not dominate the narrative.
    """
    years = max(0.0, float(years_to_retirement))
    stress_shift = max(0.0, 0.92 - float(funded_ratio)) + max(0.0, 0.78 - float(stress_pass_rate))
    pressure = max(0.0, float(event_pressure))
    youth = min(1.0, years / 25.0)
    near = min(1.0, max(0.0, 12.0 - years) / 12.0)
    mid = max(0.0, 1.0 - abs(years - 12.0) / 12.0)

    digest = hashlib.sha256(f"{seed}:{year}:{member_id}".encode("utf-8")).hexdigest()
    jitter = int(digest[:8], 16) / 0xFFFFFFFF

    scores = {
        "growth": 1.0 + youth * 0.9 - pressure * 0.30 - stress_shift * 0.55 + jitter * 0.03,
        "balanced": 1.0 + mid * 0.70 + (1.0 - stress_shift) * 0.12 + (1.0 - abs(0.5 - jitter)) * 0.02,
        "defensive": 0.9 + near * 0.85 + pressure * 0.55 + stress_shift * 0.95 + (1.0 - jitter) * 0.03,
    }
    return max(portfolio_order(), key=lambda key: (scores[key], -portfolio_order().index(key)))


def _validate_policy_from_inputs(
    inputs: SimulationPolicyValidationInputs,
    portfolio_key: str,
    *,
    max_funded_ratio_deterioration: float = 0.06,
    max_gini_worsening: float = 0.025,
    min_stress_pass_rate: float = 0.70,
) -> PolicyValidationResult:
    portfolio = MODEL_PORTFOLIOS[portfolio_key]
    neutral = MODEL_PORTFOLIOS["balanced"]
    funded_ratio_before = max(0.0, float(inputs.funded_ratio_before))
    gini_before = max(0.0, float(inputs.gini_before))
    intergen_before = max(0.0, float(inputs.intergen_before))
    stress_pass_rate_before = max(0.0, min(1.0, float(inputs.stress_pass_rate_before)))
    expected_inflation = max(0.0, float(inputs.expected_inflation))
    retiree_share = max(0.0, min(1.0, float(inputs.retiree_share)))
    near_retire_share = max(0.0, min(1.0, float(inputs.near_retire_share)))

    hedge_bonus = portfolio.inflation_hedge * (0.03 + expected_inflation)
    liability_drag = (expected_inflation * 0.8) + (retiree_share * 0.02) - hedge_bonus
    funded_ratio_after = max(0.0, funded_ratio_before * (1.0 + portfolio.expected_return - liability_drag))
    funded_ratio_deterioration = max(0.0, funded_ratio_before - funded_ratio_after)

    gini_worsening = (
        portfolio.fairness_pressure * (0.45 + near_retire_share)
        + max(0.0, expected_inflation - portfolio.inflation_hedge * 0.04) * 0.15
    )
    gini_after = gini_before + gini_worsening

    stress_pass_rate = min(
        0.99,
        max(
            0.0,
            stress_pass_rate_before
            + (neutral.stress_drawdown - portfolio.stress_drawdown) * 6.00
            + (portfolio.inflation_hedge - neutral.inflation_hedge) * 1.50
            + (portfolio.expected_return - neutral.expected_return) * 0.08
            - (near_retire_share * 0.08),
        ),
    )
    intergen_after = max(0.0, intergen_before - gini_worsening * 0.65)

    if funded_ratio_deterioration > max_funded_ratio_deterioration:
        reason = (
            f"Blocked: projected funded ratio would fall from {funded_ratio_before:.1%} "
            f"to {funded_ratio_after:.1%}, beyond the allowed deterioration corridor."
        )
        passes = False
    elif gini_worsening > max_gini_worsening:
        reason = (
            f"Blocked: projected fairness dispersion would worsen from Gini "
            f"{gini_before:.3f} to {gini_after:.3f}, beyond the configured tolerance."
        )
        passes = False
    elif stress_pass_rate < min_stress_pass_rate:
        reason = (
            f"Blocked: estimated stress pass rate would fall to {stress_pass_rate:.1%}, "
            f"below the {min_stress_pass_rate:.0%} floor."
        )
        passes = False
    else:
        reason = (
            f"Passes guardrails: funded ratio {funded_ratio_before:.1%} → {funded_ratio_after:.1%}, "
            f"Gini {gini_before:.3f} → {gini_after:.3f}, stress pass rate {stress_pass_rate:.1%}."
        )
        passes = True

    return PolicyValidationResult(
        portfolio_key=portfolio_key,
        passes=passes,
        reason=reason,
        funded_ratio_before=funded_ratio_before,
        funded_ratio_after=funded_ratio_after,
        funded_ratio_deterioration=funded_ratio_deterioration,
        gini_before=gini_before,
        gini_after=gini_after,
        gini_worsening=gini_worsening,
        stress_pass_rate=stress_pass_rate,
        intergen_before=intergen_before,
        intergen_after=intergen_after,
    )


def member_portfolio_preference(member: Member, *, valuation_year: int) -> str:
    """Deterministic MVP preference heuristic for the Sandbox preview.

    This is *not* the governance rule. It is only the local Sandbox preview
    so the page can show an indicative tally before any live Sepolia votes are
    collected.
    """
    years_to_retirement = member.years_to_retirement(valuation_year)
    if not member.active or years_to_retirement <= 5:
        return "defensive"
    if years_to_retirement <= 15:
        return "balanced"
    return "growth"


def build_indicative_support(
    members: Sequence[Member],
    weights: Sequence[VoteSnapshotRow],
    *,
    valuation_year: int,
) -> tuple[list[dict[str, object]], str]:
    """Build a deterministic preview tally from the sandbox member set."""
    members_by_wallet = {str(member.wallet): member for member in members}
    tallies = {key: 0 for key in MODEL_PORTFOLIOS}
    for row in weights:
        member = members_by_wallet.get(str(row.wallet))
        if member is None:
            continue
        choice = member_portfolio_preference(member, valuation_year=valuation_year)
        tallies[choice] += int(row.published_weight)

    total_weight = max(1, sum(tallies.values()))
    ranked = sorted(
        portfolio_order(),
        key=lambda key: (-tallies[key], portfolio_order().index(key)),
    )
    winner_key = ranked[0]
    support_rows: list[dict[str, object]] = []
    for key in portfolio_order():
        tally = tallies[key]
        support_rows.append(
            {
                "key": key,
                "name": MODEL_PORTFOLIOS[key].name,
                "weighted_votes": tally,
                "support_share": tally / total_weight,
                "support_label": f"{(tally / total_weight):.1%}",
                "allocation_hash": allocation_hash(key),
                "indicative": "Deterministic sandbox preview",
            }
        )
    return support_rows, winner_key


def validate_policy(
    ledger: CohortLedger,
    portfolio_key: str,
    *,
    max_funded_ratio_deterioration: float = 0.06,
    max_gini_worsening: float = 0.025,
    min_stress_pass_rate: float = 0.70,
) -> PolicyValidationResult:
    """Scenario-based guardrail validation for publication.

    This is the economic check that determines whether the ballot winner may
    be published on chain. It uses the scheme's current funding and fairness
    state plus declared portfolio risk characteristics. It is intentionally
    modest: serious enough to reject obviously unsuitable policies, while
    staying transparent about being a guardrail layer rather than a full asset
    allocation optimizer.
    """
    members = list(ledger.get_all_members())
    cohort_valuation = ledger.cohort_valuation()
    mwrs = {
        int(cohort): float(row["money_worth_ratio"])
        for cohort, row in cohort_valuation.items()
    }
    gini_before = float(mwr_gini(mwrs)) if len(mwrs) >= 2 else 0.0
    intergen_before = float(intergenerational_index(mwrs)) if len(mwrs) >= 2 else 1.0
    total_epv_benefits = sum(float(row["epv_benefits"]) for row in cohort_valuation.values())
    total_contributions = sum(float(member.total_contributions) for member in members)
    funded_ratio_before = total_contributions / total_epv_benefits if total_epv_benefits > 0 else 0.0

    total_members = max(1, len(members))
    active_members = sum(1 for member in members if member.active)
    retiree_share = max(0.0, 1.0 - (active_members / total_members))
    near_retire_share = sum(
        1 for member in members
        if member.active and member.years_to_retirement(ledger.valuation_year) <= 10
    ) / total_members

    return _validate_policy_from_inputs(
        SimulationPolicyValidationInputs(
            funded_ratio_before=funded_ratio_before,
            gini_before=gini_before,
            intergen_before=intergen_before,
            stress_pass_rate_before=0.94,
            expected_inflation=max(0.0, float(ledger.expected_inflation)),
            retiree_share=retiree_share,
            near_retire_share=near_retire_share,
        ),
        portfolio_key,
        max_funded_ratio_deterioration=max_funded_ratio_deterioration,
        max_gini_worsening=max_gini_worsening,
        min_stress_pass_rate=min_stress_pass_rate,
    )


def validate_simulated_policy(
    portfolio_key: str,
    inputs: SimulationPolicyValidationInputs,
    *,
    max_funded_ratio_deterioration: float = 0.06,
    max_gini_worsening: float = 0.03,
    min_stress_pass_rate: float = 0.54,
) -> PolicyValidationResult:
    """Twin-friendly guardrail check using simulated scheme state."""
    return _validate_policy_from_inputs(
        inputs,
        portfolio_key,
        max_funded_ratio_deterioration=max_funded_ratio_deterioration,
        max_gini_worsening=max_gini_worsening,
        min_stress_pass_rate=min_stress_pass_rate,
    )


def build_ballot_draft(
    ledger: CohortLedger,
    *,
    round_name: str,
    opens_at: int,
    closes_at: int,
    scale: int = DEFAULT_WEIGHT_SCALE,
) -> BallotDraft:
    members = list(ledger.get_all_members())
    weights = tuple(compute_vote_snapshot(members, scale=scale))
    support_rows, winner_key = build_indicative_support(
        members,
        weights,
        valuation_year=int(ledger.valuation_year),
    )
    validation_by_portfolio = {
        key: validate_policy(ledger, key)
        for key in portfolio_order()
    }
    return BallotDraft(
        round_name=round_name,
        opens_at=int(opens_at),
        closes_at=int(closes_at),
        portfolio_order=tuple(portfolio_order()),
        weight_rows=weights,
        support_rows=tuple(support_rows),
        winner_key=winner_key,
        winner_validation=validation_by_portfolio[winner_key],
        validation_by_portfolio=validation_by_portfolio,
    )


__all__ = [
    "ASSET_UNIVERSE",
    "MAX_EFFECTIVE_SHARE",
    "MIN_VOTERS_FOR_STRICT_CAP",
    "DEFAULT_WEIGHT_SCALE",
    "ModelPortfolio",
    "VoteSnapshotRow",
    "PolicyValidationResult",
    "BallotDraft",
    "MODEL_PORTFOLIOS",
    "SimulationPolicyValidationInputs",
    "validate_allocation",
    "portfolio_catalog",
    "portfolio_order",
    "allocation_hash",
    "decision_window_contributions",
    "compute_vote_snapshot",
    "compute_vote_snapshot_from_inputs",
    "member_portfolio_preference",
    "simulate_member_portfolio_preference",
    "build_indicative_support",
    "validate_policy",
    "validate_simulated_policy",
    "build_ballot_draft",
]
