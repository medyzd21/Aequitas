# Aequitas — Reflex frontend (Phase 1)

A product-style dashboard that sits on top of the existing Aequitas Python
actuarial engine and Solidity contracts. Reflex replaces Streamlit as the
primary frontend; Streamlit (`app.py` at the repo root) is kept alive until
this app reaches full feature parity.

## What Phase 1 covers

| Section | Migrated |
|---|---|
| Home / Fund Overview | yes — KPI strip, fund projection, cohort signals, latest events |
| Members & Cohorts | yes — roster, cohort composition, valuation table, drill-down |
| Fairness & Governance | yes — MWR by cohort, Gini, intergen index, governance sandbox |
| Operations / Event Feed | yes — human-readable timeline + hash-chain audit state |
| On-Chain / Contracts | yes — deployment table, action cards, JSON in expanders |
| How Aequitas Works | yes — lifecycle cards + SVG contract interaction map |

**Deferred to Phase 2** (still available in the Streamlit app):
stochastic fairness stress with six knobs, Monte-Carlo fan charts with
percentile tables, and the 100k synthetic population simulator.

## Prerequisites

- Python 3.10+
- A dedicated venv inside `reflex_app/` (recommended — keeps Reflex's
  NextJS/node bundle isolated from the Streamlit venv)

## Run

From `reflex_app/`:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -r ../requirements.txt
reflex init
reflex run
```

Notes (do NOT paste these into the terminal):

- `reflex init` only needs to run the first time; subsequent launches are just `reflex run`.
- On Windows the activate line is `.venv\Scripts\activate`.
- The second `pip install` pulls the engine's own dependencies (numpy,
  pandas, pydantic, altair, ...) because Reflex runs the Python actuarial
  engine in-process.

Then open http://localhost:3000.

The Reflex app reuses the actuarial engine by prepending the repo root to
`sys.path` at startup — no engine code is duplicated.

## Structure

```
reflex_app/
├── rxconfig.py                  Reflex config (app_name = aequitas_rx)
├── requirements.txt             extra deps (reflex only)
├── README.md                    (you are here)
└── aequitas_rx/
    ├── __init__.py
    ├── aequitas_rx.py           app entry + route wiring
    ├── state.py                 AppState + service layer (engine bridge)
    ├── theme.py                 palette, card styles, spacing tokens
    ├── components.py            navbar, shell, KPI strip, ribbons, cards
    └── pages/
        ├── __init__.py
        ├── overview.py          Home / Fund Overview
        ├── members.py           Members & Cohorts + drill-down
        ├── fairness.py          Fairness & Governance + sandbox
        ├── operations.py        Operations / Event Feed
        ├── contracts.py         On-Chain / Contracts + action cards
        └── how_it_works.py      Lifecycle cards + contract map
```

## Backend is untouched

- `engine/` — unchanged
- `contracts/` — unchanged
- `tests/` — unchanged (57 Python tests still pass)
- `app.py` (Streamlit) — unchanged
- `run_app.py` — unchanged

If Reflex ever breaks, the Streamlit app remains a fully working fallback.

## Phase 2 (not in this PR)

- Port Monte-Carlo percentile tables and fan charts
- Port the stochastic fairness-stress panel
- Build the 100k synthetic population simulator (new capability)
- Multi-user session state (Phase 1 is single-user demo)
- Real-time on-chain reads via web3.py instead of `deployments/latest.txt`
