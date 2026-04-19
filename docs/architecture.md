# Aequitas — Architecture Crib Sheet

One page mapping the actuarial / economic theory to the Python module or
Solidity contract that enforces it. Use this as the slide-behind-the-slides
for the capstone talk.

## The split in one sentence

The **actuarial brain lives in Python**; the **pension constitution lives
on chain**. The engine computes EPVs, MWRs, Gini, and Monte-Carlo stress.
The contracts only execute: register, mint PIUs, gate unfair proposals,
pool savings, pay streams, release reserves.

---

## Theory → enforcement map

| # | Concept | Formal definition | Off-chain computer | On-chain enforcer |
|---|---|---|---|---|
| 1 | **Expected Present Value** (EPV) | `EPV = Σ_t v^t · p_x(t) · CF_t` | `engine/actuarial.py` (Gompertz-Makeham survival + discount) → `engine/ledger.py` (`cohort_valuation`) | `FairnessGate.setBaseline` stores the 1e18-scaled EPV vector |
| 2 | **Money's Worth Ratio** | `MWR = EPV_benefits / EPV_contributions` | `engine/ledger.ValuationSummary.money_worth_ratio`; aggregated in `engine/fairness.py` | — (reporting only; not enforced on chain) |
| 3 | **Fairness corridor** | `max_{i,j} ‖ΔEPVᵢ − ΔEPVⱼ‖ / benchmark ≤ δ` | `engine.fairness.fairness_corridor_check` | `FairnessGate.submitAndEvaluate` — pairwise int256 check, reverts/rejects on breach |
| 4 | **Stochastic stress** | `m_c^(s) = 1 + β_c·F^(s) + ε_c^(s)`; summary = p95 Gini, corridor pass-rate, youngest-poor rate | `engine/fairness_stress.stochastic_cohort_stress` | `StressOracle.updateStressLevel(level, reason, dataHash)` — 1e18-scaled level + bytes32 provenance |
| 5 | **Mortality pooling** (tontine) | Deceased shares burnt, assets stay → NAV/share rises for survivors | (mirrored in `engine/simulation.py` mortality draws) | `LongevaPool.releaseMortalityCredit(wallet)` — burns shares, retains assets |
| 6 | **Mortality oracle** | Authoritative death signal | — (trusted input) | `MortalityOracle.confirmDeath` / `isDeceased` — operator-gated, proof-hashed, revocable |
| 7 | **Benefit stream** | `accrual(t) = B_annual · (t − t_last) / year`, halting at death | `engine/projection.project_member` shows the target rate | `BenefitStreamer.claim()` — linear accrual, self-stops when oracle marks death |
| 8 | **Retirement opening** | Move reserve from pool → streamer, start stream | `engine.ledger.value_member` gives the target `B_annual` | `VestaRouter.openRetirement(wallet, funding, B_annual)` — atomic `payTo → fund → startStream` |
| 9 | **Tail-risk backstop** | Seed reserve R; release only if `stress ≥ θ` and `amount ≤ cap · R` | `engine/simulation.simulate_fund` computes target R from p95 shortfall | `BackstopVault.deposit` / `release` — stress-gated, per-call capped, reentrancy-safe |
| 10 | **Audit chain** | Tamper-evident log of governance events | `engine/chain_stub.EventLog` (sha-256 chained) | All contracts `emit` role-tagged events; the chain itself is the log |

## Bridge (the translation layer)

`engine/chain_bridge.py` turns Python objects into the exact calldata each
contract expects:

* PIU balances and EPVs → int/uint-256 scaled by 1e18
* Cohort buckets → uint16, `floor(birthYear / 5) · 5`
* Stress level → uint256 in `[0, 1e18]`
* Reason codes / data hashes → bytes32 (right-padded string or SHA-256)
* Addresses → `0x` + 40 hex, short demo ids auto zero-padded

`engine/deployments.py` reads `contracts/deployments/latest.txt` (written
by `Deploy.s.sol`) so the Streamlit Contracts tab can show both the payload
and the destination address.

## Roles / trust boundary

```
owner  ─── grantRole/revokeRole on every contract
reporter ─ MortalityOracle.ORACLE, StressOracle.REPORTER
operator ─ VestaRouter.OPERATOR (opens retirements)
guardian ─ BackstopVault.GUARDIAN (pulls reserve when stressed)
router   ─ LongevaPool.PAYOUT, BenefitStreamer.FUNDER + STREAM_ADMIN
                      (granted in Deploy.s.sol so router is atomic)
```

No contract trusts another contract's word — they trust the role. No
off-chain computation is accepted unless its effect lives inside a bounded
execution rule (corridor, cap, threshold).

## Why this is a research contribution — in three bullets

1. **Intergenerational fairness is enforced, not just measured.** The
   corridor is a math-level invariant written into `FairnessGate` —
   governance cannot merge a proposal that breaks it, even by vote.
2. **Actuarial honesty, DeFi execution.** The Python engine is the same
   math a UK actuary would sign off on; the on-chain rails make it
   auditable, composable, and automatable without rewriting the model.
3. **Stress → reserve is mechanical.** A Monte-Carlo number flows from
   Python to `StressOracle`, and only then can `BackstopVault` release —
   removing discretionary bailout risk without removing human guardrails
   (caps, multisig, revocation).
