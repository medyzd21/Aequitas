"""Structured event types for the Aequitas system simulator.

The digital-twin simulator (`engine.system_simulation`) emits a stream of
these events as it runs. Each event has a plain-Python representation and
a one-line human-readable message for the Reflex UI.

Why a separate module:

* `engine.chain_stub.EventLog` already exists and is tamper-evident; this
  module is *not* a replacement for it. The simulator uses `SimEvent` for
  structured in-memory summarisation (so the UI can render a timeline),
  and writes parallel entries to `EventLog` so the audit chain stays
  consistent with the chain_bridge story.

* Every `SimEvent.kind` maps to exactly one Solidity contract that would
  fire the equivalent state change on-chain. This is the Python-is-truth
  / Solidity-is-execution mapping made explicit.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any


# ---------------------------------------------------------------------------
# Event kinds — keep these stable, the UI and audit chain both key off them.
# ---------------------------------------------------------------------------

JOIN              = "join"
CONTRIBUTION      = "contribution_batch"
RETIREMENT        = "retirement"
DEATH             = "death"
INVESTMENT_RETURN = "investment_return"
MARKET_CRASH      = "market_crash"
MORTALITY_SPIKE   = "mortality_spike"
INFLATION_SHOCK   = "inflation_shock"
PROPOSAL          = "proposal_evaluated"
STRESS_RUN        = "stress_run"
BACKSTOP_DEPOSIT  = "backstop_deposit"
BACKSTOP_RELEASE  = "backstop_release"
YEAR_CLOSED       = "year_closed"


# ---------------------------------------------------------------------------
# Contract mapping — which Solidity contract would execute this event.
# ---------------------------------------------------------------------------

# Every mapping below names a real function in contracts/src/*.sol.
# This is enforced by tests/test_events.py so a contract rename here
# fails CI and gets caught before the UI shows a stale pill.
CONTRACT_MAP: dict[str, str] = {
    JOIN:              "CohortLedger.registerMember",
    CONTRIBUTION:      "CohortLedger.contribute",
    RETIREMENT:        "VestaRouter.openRetirement",
    DEATH:             "MortalityOracle.confirmDeath",
    INVESTMENT_RETURN: "LongevaPool.harvestYield",
    MARKET_CRASH:      "StressOracle.updateStressLevel",
    MORTALITY_SPIKE:   "MortalityOracle.confirmDeath",
    INFLATION_SHOCK:   "StressOracle.updateStressLevel",
    PROPOSAL:          "FairnessGate.submitAndEvaluate",
    STRESS_RUN:        "StressOracle.updateStressLevel",
    BACKSTOP_DEPOSIT:  "BackstopVault.deposit",
    BACKSTOP_RELEASE:  "BackstopVault.release",
    YEAR_CLOSED:       "—",
}


# ---------------------------------------------------------------------------
# Severity / pill colouring — simple heuristic used by the UI timeline.
# ---------------------------------------------------------------------------

SEVERITY_MAP: dict[str, str] = {
    JOIN:              "muted",
    CONTRIBUTION:      "muted",
    RETIREMENT:        "muted",
    DEATH:             "muted",
    INVESTMENT_RETURN: "muted",
    MARKET_CRASH:      "bad",
    MORTALITY_SPIKE:   "warn",
    INFLATION_SHOCK:   "warn",
    PROPOSAL:          "good",
    STRESS_RUN:        "muted",
    BACKSTOP_DEPOSIT:  "good",
    BACKSTOP_RELEASE:  "warn",
    YEAR_CLOSED:       "muted",
}


# ---------------------------------------------------------------------------
# SimEvent dataclass
# ---------------------------------------------------------------------------

@dataclass
class SimEvent:
    """One event emitted by the system simulator.

    `year` is absolute (e.g. 2030). `kind` is one of the string constants
    above. `data` is free-form context — the UI formats it via `message()`.
    """
    year: int
    kind: str
    data: dict[str, Any] = field(default_factory=dict)

    # ------------------------------------------------------------------
    @property
    def contract(self) -> str:
        return CONTRACT_MAP.get(self.kind, "—")

    @property
    def severity(self) -> str:
        return SEVERITY_MAP.get(self.kind, "muted")

    def message(self) -> str:
        """Short human-readable sentence for the UI timeline."""
        d = self.data or {}
        y = self.year
        if self.kind == JOIN:
            return f"{y}: {d.get('count', 0)} new members joined."
        if self.kind == CONTRIBUTION:
            total = d.get("total", 0.0) or 0.0
            return f"{y}: contributions totalling £{total:,.0f}."
        if self.kind == RETIREMENT:
            return (f"{y}: {d.get('count', 0)} members retired "
                    f"(annual benefits locked).")
        if self.kind == DEATH:
            return f"{y}: {d.get('count', 0)} deaths attested."
        if self.kind == INVESTMENT_RETURN:
            r = d.get("return", 0.0) or 0.0
            return f"{y}: investment return {r:+.2%}."
        if self.kind == MARKET_CRASH:
            drop = d.get("drop", 0.0) or 0.0
            return f"{y}: MARKET CRASH — fund NAV dropped {drop:.0%}."
        if self.kind == MORTALITY_SPIKE:
            mult = d.get("multiplier", 1.0) or 1.0
            return (f"{y}: mortality spike — force of mortality "
                    f"×{mult:.2f} for this year.")
        if self.kind == INFLATION_SHOCK:
            infl = d.get("inflation", 0.0) or 0.0
            return f"{y}: inflation shock {infl:.1%} — benefits indexed."
        if self.kind == PROPOSAL:
            name = d.get("name", "Reform")
            verdict = "PASSED" if d.get("passes") else "FAILED"
            return f"{y}: proposal '{name}' {verdict} the fairness corridor."
        if self.kind == STRESS_RUN:
            prate = d.get("pass_rate", 0.0) or 0.0
            return (f"{y}: stress run — corridor pass rate {prate:.0%}.")
        if self.kind == BACKSTOP_DEPOSIT:
            return (f"{y}: backstop reserve topped up by "
                    f"£{d.get('amount', 0):,.0f}.")
        if self.kind == BACKSTOP_RELEASE:
            return (f"{y}: backstop released £{d.get('amount', 0):,.0f} "
                    f"to cover a shortfall.")
        if self.kind == YEAR_CLOSED:
            fr = d.get("funded_ratio", 0.0) or 0.0
            return f"{y}: year closed — funded ratio {fr:.0%}."
        return f"{y}: {self.kind}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "year":     int(self.year),
            "kind":     self.kind,
            "contract": self.contract,
            "severity": self.severity,
            "message":  self.message(),
            **{f"data_{k}": v for k, v in (self.data or {}).items()},
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def summarise_events(events: list[SimEvent]) -> dict[str, int]:
    """Count events by kind — handy for the UI timeline headline."""
    out: dict[str, int] = {}
    for e in events:
        out[e.kind] = out.get(e.kind, 0) + 1
    return out


__all__ = [
    "JOIN", "CONTRIBUTION", "RETIREMENT", "DEATH", "INVESTMENT_RETURN",
    "MARKET_CRASH", "MORTALITY_SPIKE", "INFLATION_SHOCK", "PROPOSAL",
    "STRESS_RUN", "BACKSTOP_DEPOSIT", "BACKSTOP_RELEASE", "YEAR_CLOSED",
    "CONTRACT_MAP", "SEVERITY_MAP",
    "SimEvent", "summarise_events",
]
