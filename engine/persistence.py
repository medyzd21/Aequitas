"""Save / load the CohortLedger to disk as JSON.

Keeps the app hot-reload-friendly during development and lets the user
checkpoint demo state between PyCharm runs.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from engine.ledger import CohortLedger
from engine.models import Member


def to_dict(ledger: CohortLedger) -> dict[str, Any]:
    return {
        "piu_price": ledger.piu_price,
        "valuation_year": ledger.valuation_year,
        "discount_rate": ledger.discount_rate,
        "salary_growth": ledger.salary_growth,
        "investment_return": ledger.investment_return,
        "members": [m.to_dict() for m in ledger.members.values()],
        "cohort_aggregate_contrib": {
            str(k): v for k, v in ledger.cohort_aggregate_contrib.items()
        },
    }


def from_dict(payload: dict[str, Any]) -> CohortLedger:
    ledger = CohortLedger(
        piu_price=float(payload.get("piu_price", 1.0)),
        valuation_year=int(payload.get("valuation_year", 2026)),
        discount_rate=float(payload.get("discount_rate", 0.04)),
        salary_growth=float(payload.get("salary_growth", 0.025)),
        investment_return=float(payload.get("investment_return", 0.05)),
    )
    for m in payload.get("members", []):
        ledger.members[m["wallet"]] = Member(**m)
    ledger.cohort_aggregate_contrib = {
        int(k): float(v)
        for k, v in payload.get("cohort_aggregate_contrib", {}).items()
    }
    return ledger


def save(ledger: CohortLedger, path: str | Path) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(to_dict(ledger), indent=2))
    return p


def load(path: str | Path) -> CohortLedger:
    p = Path(path)
    return from_dict(json.loads(p.read_text()))
