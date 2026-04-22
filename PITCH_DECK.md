# Aequitas — Pitch Deck Script

**A Hybrid Actuarial–Blockchain Pension Protocol**
Master's capstone · 15-minute pitch · 8 slides

---

## Opening hook (first 20 seconds, spoken before Slide 1 lands)

> "In the UK alone, two-and-a-half trillion pounds sits in pension funds. Nobody in this room — not the regulators, not the trustees, not the actuaries, and certainly not the members — can tell you, on demand, whether that money is being divided fairly between the generations that paid it in. That is the question Aequitas is built to answer."

---

## Slide 1 — Title

**Title:** AEQUITAS — A Hybrid Actuarial–Blockchain Pension Protocol

**Visual:** Project name in large type, one-line tagline underneath, subtle geometric motif (concentric cohort rings, or a horizontal "fairness corridor" band). Author, institution and date in the footer.

**On-slide text:**

- AEQUITAS
- A Hybrid Actuarial–Blockchain Pension Protocol
- *"Pensions you can verify — generation by generation."*
- [Your name] · [Institution] · Master's Capstone · 2026

**Speaker script (≈45 s):**

"Good afternoon. My name is Yazid. For the next fifteen minutes I'd like to show you a system that answers a question our pension industry has been avoiding for forty years: *is my pension fair?* Not fair in principle — fair to *me*, to *my cohort*, and to the generation after us. The project is called Aequitas, and it sits at the intersection of actuarial science and smart-contract engineering."

**Why this slide matters:** Sets the tone as ambitious and serious. Frames Aequitas as an answer to a *real* actuarial question, not a crypto novelty.

---

## Slide 2 — The problem

**Title:** Pensions Are Opaque, Unfair, and Fragmented

**Visual:** A 2 × 2 grid. Each quadrant has a simple icon and a two-word label. Under the grid, a single italic line: *"Each is solvable with existing actuarial science. None is solved in practice."*

**On-slide bullets:**

- **Opacity** — members sign a 30-year contract they cannot independently verify.
- **Intergenerational unfairness** — cohorts silently cross-subsidise one another through reforms that are hard to audit and almost impossible to reverse.
- **Inefficient decumulation** — retail annuity markets offer poor money's-worth; longevity pooling is rare outside insurance.
- **Disconnected solvency guardrails** — stress tests live in regulator spreadsheets, not in the member's view.

**Speaker script (≈90 s):**

"Pension systems have four structural problems that have quietly compounded over the last three decades.

They are **opaque** — a member signs a thirty-year contract they cannot independently verify.

They are **intergenerationally unfair** — cohorts silently cross-subsidise one another through reforms that are difficult to audit and almost impossible to undo.

**Decumulation is inefficient** — the annuity market offers poor money's-worth, and longevity risk is rarely properly pooled outside insurance.

And the **solvency machinery** — stress tests, backstops, reserves — runs *separately* from the member's own view of the system.

Each of these is solvable with existing actuarial mathematics. None of them is solved in practice. That is the gap Aequitas addresses."

**Why this slide matters:** Establishes credibility by naming four *real, diagnosed* pension failures. Any actuarial reader will recognise them immediately; any non-specialist still understands them.

---

## Slide 3 — The solution

**Title:** Aequitas — One Hybrid System, Two Layers

**Visual:** Clean horizontal diagram. Left block: "**Python engine** — actuarial truth." Right block: "**8 Solidity contracts** — execution, governance, audit." A labelled bridge between them: "**chain_bridge** — one-to-one event mapping." Top banner in muted accent: *"Verifiable pensions, by cohort, through time."*

**On-slide text (sparse — the diagram does most of the work):**

- **Python engine** = actuarial truth (peer-reviewable, deterministic, tested)
- **Solidity contracts** = execution, governance, audit (tamper-evident, public, composable)
- **Chain bridge** = every engine event maps to exactly one contract call

**Speaker script (≈75 s):**

"The design principle is deliberately simple. The actuarial engine — the source of truth for every number in the system — lives in Python, where it can be independently peer-reviewed like any other actuarial model. The *execution*, the *governance rules*, and the *audit trail* live on-chain, where they become tamper-evident and publicly verifiable.

Every event the Python engine emits has a single corresponding Solidity contract that would execute it on-chain. That one-to-one mapping is the hybrid principle — and it avoids the two common failures of blockchain projects in finance: putting too much logic on-chain, or too little."

**Why this slide matters:** Neutralises the "blockchain bloat" objection *before* the technical slides begin. In one image the jury sees how actuarial rigor and chain guarantees coexist.

---

## Slide 4 — The actuarial core

**Title:** Four Actuarial Primitives

**Visual:** Four horizontal rows. Each row has a name, a one-line plain-English gloss, and a small muted box containing the equation.

**On-slide content:**

1. **Expected Present Value (EPV)** — the actuarial price of a future cashflow.
   `EPV = Σ vᵗ · ₜpₓ · CFₜ`

2. **Money Worth Ratio (MWR)** — what a cohort gets back per £ paid in. Parity = 1.
   `MWR = EPV(benefits) / EPV(contributions)`

3. **Fairness corridor** — cap on how much any reform may move one cohort relative to another.
   `max_{i,j} |ΔMWRᵢ − ΔMWRⱼ| / parity ≤ δ`

4. **Longevity pooling** — survivors inherit shares of deceased members' balances (the *mortality credit*, continuously updated).

**Speaker script (≈110 s):**

"At the heart of the system sit four actuarial primitives. Nothing exotic — all standard textbook machinery.

The **Expected Present Value** is the classical actuarial price of a promised cashflow.

The **Money Worth Ratio** tells you, per cohort, whether members are getting back what they paid in. Parity is one; below one means the cohort is subsidising someone else; above one means it's being subsidised.

The **fairness corridor** is the novel contribution: we require that no governance reform may widen the gap between any two cohorts' MWR changes by more than a small delta — typically five percent. This is enforced as a function, not as a principle.

And **longevity pooling** redistributes the balances of deceased members to their surviving cohort — the mortality credit, familiar to anyone who has worked on variable annuities.

Every governance action the system executes is tested against these four quantities *before* it is allowed to fire."

**Why this slide matters:** Earns the actuarial professor's trust. Shows the original contribution — the fairness corridor as an enforceable mechanism — without hiding behind notation.

---

## Slide 5 — The on-chain surface

**Title:** Eight Contracts, Three Responsibilities

**Visual:** Three vertical columns, each a small card containing contract pills.

- **Bookkeeping & accumulation**
  - CohortLedger — members & Personal Income Units (PIUs)
  - LongevaPool — survivor pool & mortality credits

- **Decumulation & oversight**
  - VestaRouter — retirement entry
  - BenefitStreamer — benefit streams & survivors
  - MortalityOracle — death attestation

- **Governance & resilience**
  - FairnessGate — corridor enforcement
  - StressOracle — market / longevity shocks
  - BackstopVault — reserve releases

**Speaker script (≈90 s):**

"The on-chain surface is eight Solidity contracts, each with a narrow, testable responsibility, grouped into three layers.

The **bookkeeping layer** — CohortLedger and LongevaPool — records what every member has paid in, in PIUs, and what each cohort collectively owns, including the mortality credits returned by the survivor pool.

The **decumulation layer** — VestaRouter, BenefitStreamer, MortalityOracle — manages the retirement lifecycle: opening an annuity, streaming benefits, and attesting deaths.

The **governance layer** — FairnessGate, StressOracle, BackstopVault — enforces the fairness corridor, ingests stress signals, and releases reserves when the system breaches a threshold.

All eight contracts are written, tested under Foundry, and deploy to a local chain with a single script."

**Why this slide matters:** Lets the blockchain jury see real contracts with real responsibilities. The three-layer grouping is easier to remember than eight independent modules, and the wording — "narrow, testable" — signals engineering discipline.

---

## Slide 6 — Why blockchain (and why *not* for the sake of it)

**Title:** What Blockchain Actually Adds

**Visual:** Three short cards across the slide. A footer line in italics, slightly muted, naming what is deliberately *off-chain*.

**On-slide content:**

1. **Enforcement** — a reform that fails the corridor *cannot* execute; `FairnessGate.submitAndEvaluate` reverts.

2. **Auditability** — every contribution, death attestation, benefit payment and proposal is on a tamper-evident chain, indexed by cohort, replayable years later.

3. **Composability** — reserves, stress oracles and backstops connect to other schemes and external capital markets without bespoke integrations.

Footer (muted): *What stays off-chain: salaries, mortality tables, stochastic stress — every actuarial input that requires peer-reviewed engines or private data. The chain enforces; Python computes.*

**Speaker script (≈90 s):**

"The natural question: *why blockchain at all?* Three answers — and one thing to notice about what isn't on-chain.

First, **enforcement**. The fairness corridor is not a trustee recommendation; it is a function that reverts. A reform that would widen intergenerational inequality cannot be executed by anyone, including the scheme's own administrators.

Second, **auditability**. Every action is recorded on a public, tamper-evident ledger, indexed by cohort, replayable years later — which is how a pension contract actually ought to be documented, given it outlives most of the people who sign it.

Third, **composability**. Backstops, reserves and stress oracles connect to other schemes and external capital markets without bespoke integrations.

Crucially, **the actuarial computation itself stays off-chain**. Salaries, mortality tables, stochastic stress — these remain in a peer-reviewed Python engine, where actuaries can inspect them properly. The chain enforces; Python computes."

**Why this slide matters:** Directly answers the single most predictable jury objection. The *what-is-off-chain* footer is the hardest-to-argue-against line in the whole deck.

---

## Slide 7 — Prototype proof

**Title:** This Is Not a Concept — It Runs

**Visual:** 2 × 2 grid of four app screenshots from the Reflex app (see recommendations below), each with a small caption. A bold footer strip with four hard numbers:

`8 Solidity contracts · 93 Python tests · 6 scenarios · end-to-end demo in ~7 s`

**On-slide bullets:**

- Reflex product interface with seven views: Overview · Members · Fairness · **Digital Twin** · Operations · Contracts · How It Works.
- **Live Digital Twin** — one click runs 30 years × 1,000 members × 200 stress scenarios.
- Every event in the twin's timeline carries the Solidity contract that would execute it on-chain.
- All eight contracts compile, pass Foundry tests, and deploy locally.

**Speaker script (≈110 s):**

"This is where the project separates from the more common 'thesis architecture' slide. Everything I have described is built.

There is a product-grade Reflex application with seven views. The one I want to draw your attention to is the **Digital Twin**. One click runs a thirty-year simulation of a thousand-member scheme — population turnover, contributions, stochastic returns, retirements, mortality, stochastic fairness stress, and governance proposals — all computed by the same actuarial engine. Every single event in the resulting timeline carries a pill showing the Solidity contract that would execute it on-chain.

Ninety-three tests pass across the actuarial engine and the contract bridge. Six scenarios run end-to-end. The system you have just heard described runs end-to-end on the laptop in front of you."

**Why this slide matters:** This is the decisive slide. It converts the deck from *"a promising idea"* to *"a delivered system."* The Digital Twin is the single most distinctive artefact — emphasise it and the hard numbers.

---

## Slide 8 — Vision & ask

**Title:** From Capstone to Pension-System Digital Twin

**Visual:** Horizontal roadmap with three connected nodes: **Today → Next → Vision**. Short caption under each. Closing tagline across the bottom.

**On-slide text:**

- **Today** — single scheme, synthetic population, local deployment, full demo.
- **Next** — calibrate against a real workplace scheme; peer-reviewed mortality tables; the twin used in live actuarial valuations.
- **Vision** — a regulator-facing pension digital twin. *Every reform simulated against the fairness corridor before it becomes law.*

Bottom tagline: *"Pensions are the longest financial contract a person ever signs. Aequitas is the first protocol that lets every party verify that contract — every year, for every cohort."*

**Speaker script (≈70 s):**

"I want to close with where this goes.

*Today*, Aequitas is a capstone with a synthetic population and a local deployment.

The *near-term* path is to calibrate it against a real scheme — a workplace plan, a university fund — so that it becomes a working digital twin used in an actual valuation.

The *longer horizon* is regulatory. A pension digital twin, sitting alongside the actuarial function, against which every proposed reform is simulated under the fairness corridor *before* it ever reaches legislation. That is a small addition to our governance toolkit, and it would eliminate an entire class of intergenerational error that pension systems currently commit in slow motion.

Thank you. I'd welcome your questions."

**Why this slide matters:** Lifts the project out of the classroom. Ends on a concrete, extensible vision the jury can picture funding or supervising. The tagline gives the audience a quotable final line.

---

## Closing line (if you want one after Q&A)

> "A pension is the longest financial contract a person ever signs. Aequitas is the first protocol that lets every party verify that contract — not at the end, but every year along the way."

---

## Five likely jury questions — with strong, concise answers

**1. "Why blockchain and not just a trusted database with digital signatures?"**
A trusted database needs a trusted party. The entire point of the fairness corridor is to make reforms *non-discretionary*: a signed database still requires someone to decide when to sign. A smart contract removes that discretion — the corridor either passes or the transaction reverts.

**2. "How do you handle off-chain inputs — salaries, deaths, market returns — that the chain cannot verify directly?"**
Through named oracles with explicit attestation. `MortalityOracle` ingests signed death attestations; `StressOracle` ingests signed market and longevity signals. The chain doesn't claim to verify reality; it verifies *who claimed reality, when, and with what evidence*, and gives you an immutable audit trail to go with it.

**3. "Isn't the fairness corridor itself a policy choice? Who sets δ?"**
Yes — δ is deliberately a policy parameter, and that's a feature, not a bug. The protocol doesn't impose a value judgement; it enforces whatever δ is chosen. Sensitivity to δ can itself be stress-tested on the twin — which is exactly what the Fairness page demonstrates.

**4. "Is this regulatorily feasible under current UK/EU pension law?"**
Not as a replacement for the trust-based legal framework — as a *parallel verification layer*. The trustee remains legally responsible; Aequitas gives the trustee and the regulator a cryptographic, cohort-level audit of every action. It's additive, not disruptive.

**5. "How does this scale beyond a thousand members to a national scheme?"**
The actuarial engine is NumPy-vectorised — a hundred thousand members still runs in seconds. The contracts scale with L2 rollups — this is ledger and governance, not high-frequency throughput. The real bottleneck is not chain capacity, it is data quality in the input schemes; that is a calibration problem, not an architecture one.

---

## Screenshot recommendations

- **Slide 3 (solution):** the *How It Works* architecture map — the diagram showing the Python engine ↔ Solidity contract bridge.
- **Slide 4 (actuarial core):** the *Fairness* page showing MWR-by-cohort bars and the stochastic stress panel side by side.
- **Slide 5 (contracts):** the *Contracts* page showing the eight deployed contracts and their action cards (actor → target pills).
- **Slide 7 (proof) — populate the 2 × 2 grid with four Digital Twin screenshots:**
  1. Digital Twin summary KPIs (final members, peak NAV, funded ratio, avg Gini).
  2. Digital Twin fund evolution chart (NAV + contributions + benefits + reserve).
  3. Digital Twin cohort-MWR trajectories (many lines, one per cohort).
  4. Digital Twin event timeline with the **contract pills visible** on the right of each row — this one is essential; it *is* the hybrid story in a single screenshot.
