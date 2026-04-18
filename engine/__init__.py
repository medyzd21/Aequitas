"""Aequitas actuarial engine package.

Modules:
    models        — dataclasses (Member, Proposal, ProjectionRow)
    actuarial     — mortality, annuity factors, EPV (expected present value)
    ledger        — CohortLedger: contributions, PIUs, cohort aggregates
    projection    — individual & fund-level projections to retirement
    fairness      — fairness corridor, MWR dispersion, intergenerational metrics
    simulation    — Monte Carlo for returns & retirement outcomes
    persistence   — JSON save/load of ledger state
    chain_stub    — append-only event log (future smart-contract mirror)
"""

__all__ = [
    "models",
    "actuarial",
    "ledger",
    "projection",
    "fairness",
    "simulation",
    "persistence",
    "chain_stub",
]
