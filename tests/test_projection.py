"""Tests for engine.projection and engine.simulation."""
from __future__ import annotations

from engine.ledger import CohortLedger
from engine.projection import project_fund, project_member
from engine.seed import seed_ledger
from engine.simulation import simulate_member


def _ledger():
    return seed_ledger(CohortLedger(valuation_year=2026))


def test_project_member_has_accumulation_and_retired_phases():
    L = _ledger()
    member = L.get_member_summary("0xA010")
    df = project_member(member, valuation_year=2026,
                        salary_growth=0.025, investment_return=0.05,
                        discount_rate=0.04, horizon=70)
    assert not df.empty
    phases = set(df.phase.unique())
    assert "accumulation" in phases
    assert "retired" in phases
    # fund never negative
    assert (df.fund_value >= -1e-6).all()


def test_project_fund_aggregates():
    L = _ledger()
    df = project_fund(L.get_all_members(), valuation_year=2026, horizon=60)
    assert not df.empty
    assert (df.contributions >= 0).all()
    assert (df.benefit_payments >= 0).all()
    # Eventually benefits should flow
    assert df.benefit_payments.sum() > 0


def test_simulate_member_percentiles_ordered():
    L = _ledger()
    m = L.get_member_summary("0xA012")
    r = simulate_member(m, valuation_year=2026, n_paths=400, seed=7)
    pct = r["percentiles"]["fund_at_retirement"].to_list()
    # quantiles monotonically increasing
    assert pct == sorted(pct)
