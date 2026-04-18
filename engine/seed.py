"""Seed a CohortLedger with the sample member CSV.

Used by the Streamlit app's “Load demo data” button and by tests.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from engine.ledger import CohortLedger


SAMPLE_CSV = Path(__file__).resolve().parent.parent / "data" / "sample_members.csv"


def seed_ledger(
    ledger: CohortLedger | None = None,
    csv_path: str | Path | None = None,
) -> CohortLedger:
    """Register every row in the CSV and credit its opening contribution."""
    if ledger is None:
        ledger = CohortLedger()
    path = Path(csv_path) if csv_path else SAMPLE_CSV
    df = pd.read_csv(path)
    for _, row in df.iterrows():
        wallet = str(row["wallet"])
        if wallet in ledger.members:
            continue
        ledger.register_member(
            wallet=wallet,
            birth_year=int(row["birth_year"]),
            salary=float(row["salary"]),
            contribution_rate=float(row["contribution_rate"]),
            retirement_age=int(row["retirement_age"]),
            sex=str(row["sex"]),
        )
        opening = float(row.get("opening_contribution", 0.0) or 0.0)
        if opening > 0:
            ledger.contribute(wallet, opening)
    return ledger
