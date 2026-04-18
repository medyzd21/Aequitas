# Aequitas

An **intergenerationally-fair pension prototype** — solo Master's capstone in
actuarial science and blockchain. Aequitas separates the *brain* (actuarial
math in Python) from the *bones* (execution rules in Solidity) and proves
that a pension scheme can keep its promises under stress while remaining
fully auditable.

```
               ┌───────────────────────── off-chain (Python engine) ─────────────────────────┐
               │  engine/actuarial  engine/ledger   engine/projection   engine/simulation    │
               │  engine/fairness   engine/fairness_stress              engine/chain_stub    │
               └──────────┬─────────────────────────────────────────────────┬────────────────┘
                          │ engine/chain_bridge  (1e18 fixed-point, uint16 cohorts, bytes32)  │
               ┌──────────▼─────────────────────────────────────────────────▼────────────────┐
               │                       on-chain (Solidity contracts)                          │
               │                                                                               │
               │   EquiGen :  CohortLedger ── FairnessGate                                     │
               │   Longeva :  MortalityOracle ── LongevaPool                                   │
               │   Vesta   :  VestaRouter ── BenefitStreamer                                   │
               │   Astra   :  StressOracle ── BackstopVault                                    │
               └───────────────────────────────────────────────────────────────────────────────┘
```

The Python engine computes EPVs, MWRs, Gini, Monte-Carlo stress, and the
fairness corridor. The Solidity contracts only *execute*: register members,
accrue PIUs, gate unfair proposals, pool savings, pay streams, and release
reserves when the off-chain stress signal crosses a threshold.

---

## Off-chain: the actuarial engine (Python)

| Module | Role |
|---|---|
| `engine/actuarial.py`       | Gompertz-Makeham life table, annuity factors, EPVs |
| `engine/ledger.py`          | `CohortLedger` — members, contributions, PIUs, per-cohort valuations |
| `engine/projection.py`      | Deterministic year-by-year path per member / per fund |
| `engine/simulation.py`      | Monte-Carlo retirement-outcome distributions |
| `engine/fairness.py`        | MVP corridor check + MWR dispersion / Gini / intergenerational index |
| `engine/fairness_stress.py` | One-factor stochastic cohort shocks and corridor pass-rate |
| `engine/chain_stub.py`      | Local append-only hashed audit log |
| `engine/chain_bridge.py`    | Translates engine output into on-chain calldata |
| `engine/persistence.py`     | JSON save/load |
| `engine/seed.py`            | Seed a ledger from `data/sample_members.csv` |

The Streamlit app (`app.py`) has ten tabs: *Overview, Members, Actuarial
Valuation, Projections, Monte Carlo, Fairness, Governance Sandbox, Fairness
Stress, Audit Chain, Contracts*. The Contracts tab previews the exact
payloads the bridge would send on chain.

### Run the Python app

```bash
pip install -r requirements.txt
streamlit run app.py
```

Click **Load demo data** in the sidebar — 15 sample members across eight
cohorts get registered and opening contributions credited.

### Run the Python tests

```bash
python -m pytest
```

---

## On-chain: the execution layer (Solidity, Foundry)

Every contract lives in `contracts/src/`. They share two tiny utility bases
(`Owned`, `Roles`) and a set of small `interfaces/` — no OpenZeppelin or
external deps, which keeps `forge test` self-contained.

| Contract | Phase | What it does |
|---|---|---|
| `CohortLedger.sol`    | EquiGen | Registers members, records contributions, mints PIUs (1e18 fixed-point), buckets birth years into 5-year cohorts. |
| `FairnessGate.sol`    | EquiGen | Holds the baseline cohort-EPV vector; any new proposal must pass the pairwise corridor `max‖ΔEPVᵢ − ΔEPVⱼ‖/benchmark ≤ δ`. |
| `MortalityOracle.sol` | Longeva | Operator confirms death events with a proof hash; downstream contracts read `deathTimestamp(wallet)`. |
| `LongevaPool.sol`     | Longeva | Share-based tontine pool. Mortality credits burn the deceased's shares, raising survivor NAV. |
| `BenefitStreamer.sol` | Vesta   | Per-retiree linear benefit stream; stops automatically on confirmed death. |
| `VestaRouter.sol`     | Vesta   | Orchestrates `pool.payTo → streamer.fund → streamer.startStream` when a member is marked retired. |
| `StressOracle.sol`    | Astra   | Mirrors the Python stress signal on chain as a 1e18-scaled level + reason code + data hash. |
| `BackstopVault.sol`   | Astra   | Holds reserve ETH; guardian can release (capped per-call) only when stress ≥ threshold. |

### Role graph (after `Deploy.s.sol`)

```
owner (EOA / multisig)
  │
  ├─ CohortLedger: REGISTRAR, CONTRIBUTION, RETIREMENT, (owner can setPiuPrice)
  ├─ FairnessGate: BASELINE, PROPOSER
  ├─ LongevaPool:  YIELD
  │
  ├─ MortalityOracle: ORACLE ──→ reporter
  ├─ StressOracle:    REPORTER ──→ reporter
  │
  ├─ LongevaPool:  DEPOSIT ──→ depositor
  ├─ BackstopVault: DEPOSITOR, GUARDIAN ──→ depositor / guardian
  │
  ├─ LongevaPool:     PAYOUT      ──→ VestaRouter
  ├─ BenefitStreamer: STREAM_ADMIN, FUNDER ──→ VestaRouter
  └─ VestaRouter:     OPERATOR ──→ operator
```

### Run the contract tests

```bash
cd contracts
forge test -vv
```

This compiles all eight contracts and runs the full Foundry suite in
`contracts/test/*.t.sol` (CohortLedger, FairnessGate, MortalityOracle,
LongevaPool, BenefitStreamer, VestaRouter, StressOracle, BackstopVault).

### Deploy the stack

**Local (anvil):**

```bash
# terminal 1
anvil

# terminal 2
cd contracts
export ANVIL_PK=0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80
forge script script/Deploy.s.sol \
    --rpc-url localhost           \
    --private-key $ANVIL_PK       \
    --broadcast
cat deployments/latest.txt
```

**Sepolia:**

```bash
cd contracts
cp .env.example .env        # fill in SEPOLIA_RPC_URL, ETHERSCAN_API_KEY, PRIVATE_KEY
source .env
forge script script/Deploy.s.sol \
    --rpc-url sepolia             \
    --private-key $PRIVATE_KEY    \
    --broadcast --verify
```

Every deploy writes `contracts/deployments/latest.txt` with the eight
addresses so the Python bridge can pick them up.

---

## End-to-end demo story

1. **Register cohorts (Python).** Load the 15-member demo → engine buckets
   them into eight birth-year cohorts, computes EPV_contributions and
   EPV_benefits per cohort and a per-cohort MWR.
2. **Publish baseline (bridge → chain).** `engine.chain_bridge.encode_baseline`
   produces a `FairnessGate.setBaseline(cohorts, epvs)` call.
3. **Submit a proposal.** A cohort multiplier vector (`{1995: 0.97, …}`) is
   encoded into `FairnessGate.submitAndEvaluate(name, cohorts, newEpvs, δ)`.
   The on-chain corridor rule accepts or rejects — same math as the Python
   `fairness_corridor_check`.
4. **Open retirement (chain).** Member is marked retired → `VestaRouter.
   openRetirement(wallet, funding, annualBenefit)` pulls from LongevaPool,
   funds BenefitStreamer, starts the stream.
5. **Stress hits (Python → chain).** `engine.fairness_stress.stochastic_
   cohort_stress` runs N scenarios, computes p95 Gini and corridor-pass
   rate. If stress ≥ 0.7, reporter calls `StressOracle.updateStressLevel`
   with the normalised number + reason.
6. **Reserve releases (chain).** Guardian calls `BackstopVault.release(amount)`
   — reverts unless `stressOracle.stressLevel() ≥ releaseThreshold`; cap at
   `perCallCapBps` of reserve balance.

---

## Repository layout

```
aequitas/
├── app.py                        Streamlit 10-tab demo
├── engine/                       off-chain actuarial brain + bridge
├── tests/                        pytest for the engine
├── data/sample_members.csv       15-member demo roster
├── contracts/
│   ├── foundry.toml              Foundry config + RPC endpoints
│   ├── .env.example              keys / role-holder overrides
│   ├── src/                      8 Solidity contracts
│   │   ├── interfaces/           5 lightweight interfaces
│   │   └── utils/                Owned, Roles (no external deps)
│   ├── test/                     8 Foundry test files
│   ├── script/Deploy.s.sol       full-stack deployment + role wiring
│   └── deployments/              addresses written here after deploy
├── requirements.txt
└── README.md                     (you are here)
```

---

## What remains unfinished / next milestones

1. Replace the Gompertz-Makeham table with a licensed national mortality
   base table (e.g. S3PMA for the UK).
2. Calibrate investment-return and salary-growth parameters from a real
   DB-scheme dataset.
3. Swap native ETH in LongevaPool / BackstopVault for an ERC-20 stablecoin
   and add an ERC-4626 LST yield adapter.
4. Put a real price oracle behind `LongevaPool.simulateYield` (Chainlink
   price feed or yield-bearing LST).
5. Chainlink-Functions / VRF upgrade for `MortalityOracle` and
   `StressOracle` so updates are computed by a decentralised oracle rather
   than an EOA reporter.
6. Governance UI with weighted cohort voting and corridor enforcement on
   chain before proposal execution.
7. LDI overlay / duration-matched asset allocation inside LongevaPool.
8. Subgraph + front-end to let retirees inspect their stream and the
   scheme-level corridor in real time.
