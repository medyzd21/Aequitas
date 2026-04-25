from __future__ import annotations

import pytest

from engine.investment_policy import (
    MAX_EFFECTIVE_SHARE,
    allocation_hash,
    build_ballot_draft,
    compute_vote_snapshot,
    validate_allocation,
)
from engine.ledger import CohortLedger
from engine.seed import seed_ledger


def _seeded_ledger() -> CohortLedger:
    return seed_ledger(CohortLedger(valuation_year=2026))


def test_validate_allocation_rejects_bad_total():
    with pytest.raises(ValueError):
        validate_allocation(
            {
                "global_equity": 50,
                "developed_sovereign_bonds": 20,
                "inflation_linked_bonds": 15,
                "gold": 10,
                "cash_reserve": 10,
            }
        )


def test_compute_vote_snapshot_is_capped_and_concave():
    ledger = _seeded_ledger()
    rows = compute_vote_snapshot(ledger.get_all_members())

    assert len(rows) >= 20
    assert sum(row.published_weight for row in rows) == 1_000_000
    assert max(row.vote_share for row in rows) <= MAX_EFFECTIVE_SHARE + 1e-9

    by_wallet = {row.wallet: row for row in rows}
    assert by_wallet["0xA016"].published_weight > by_wallet["0xA020"].published_weight
    assert by_wallet["0xA016"].raw_score < 2.01


def test_compute_vote_snapshot_rejects_impossible_cap():
    ledger = CohortLedger(valuation_year=2026)
    for idx in range(10):
        ledger.register_member(f"0x{idx + 1:04x}", 1980 + idx, salary=40_000 + idx * 1_000)
    with pytest.raises(ValueError):
        compute_vote_snapshot(ledger.get_all_members())


def test_build_ballot_draft_returns_valid_winner_and_hashes():
    ledger = _seeded_ledger()
    draft = build_ballot_draft(
        ledger,
        round_name="2026 allocation round",
        opens_at=1_800_000_000,
        closes_at=1_800_604_800,
    )

    assert draft.round_name == "2026 allocation round"
    assert draft.winner_key in {"growth", "balanced", "defensive"}
    assert draft.winner_validation.portfolio_key == draft.winner_key
    assert allocation_hash("growth").startswith("0x")
    assert len(draft.support_rows) == 3
