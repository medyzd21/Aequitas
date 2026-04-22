# Aequitas Codex Handoff

## 1. Project goal

Aequitas is a Master's capstone that turns a defined-benefit pension scheme into a hybrid actuarial + blockchain protocol. A Python actuarial engine produces all the economics (present values, money-worth ratios per cohort, a fairness corridor, stochastic stress tests, and a time-evolving digital twin). Eight Solidity contracts then record the verdicts on-chain so members, regulators, and auditors can verify every bookkeeping, governance, and treasury step. The current product vision is a jury-ready Reflex web app where a non-technical operator can see the scheme, run live on-chain actions against a Sepolia deployment through MetaMask, and audit everything that happened — without ever seeing private keys, calldata, or CLI commands by default.

## 2. Current architecture

- **Python actuarial engine** at `engine/`. This is the source of truth. Every number shown in the UI (EPV, MWR, Gini, intergen index, stress results, digital-twin trajectories) is computed here. The engine has no blockchain dependency. Key modules: `actuarial.py`, `ledger.py`, `projection.py`, `fairness.py`, `fairness_stress.py`, `system_simulation.py`, `population.py`, `scenarios.py`, `events.py`, `models.py`, plus two chain-adjacent helpers: `chain_bridge.py` (Python→Solidity call encoders, no web3 dependency) and `chain_stub.py` (tamper-evident in-memory `EventLog`).
- **Deployment registry** at `engine/deployments.py` (legacy, reads `contracts/deployments/latest.txt`) and `engine/onchain_registry.py` (new, reads `contracts/deployments/sepolia.json`). `load_any_deployment()` prefers the JSON registry and falls back to the legacy file.
- **Reflex frontend** at `reflex_app/aequitas_rx/`. Server-rendered Python UI. Seven existing pages (Overview, Members, Fairness, Digital Twin, Operations, Contracts, How It Works) plus one new page (Actions). All state lives in `AppState` (`reflex_app/aequitas_rx/state.py`). The Reflex server never holds a private key and never signs transactions itself.
- **Solidity contracts** at `contracts/src/`: `CohortLedger`, `FairnessGate`, `MortalityOracle`, `LongevaPool`, `BenefitStreamer`, `VestaRouter`, `StressOracle`, `BackstopVault`. Deploy + demo scripts at `contracts/script/` (`Deploy.s.sol`, `DemoFlow.s.sol`). Foundry toolchain.
- **Sepolia deployment** is assumed live (per the move instructions). The registry file `contracts/deployments/sepolia.json` currently has the Sepolia header but `"contracts": {}` — it has **not** been populated with the 8 deployed addresses yet.
- **MetaMask / browser wallet layer** at `reflex_app/aequitas_rx/assets/wallet_bridge.js`. Exposes `window.aequitasWallet.{connect, switchToSepolia, runAction}`. Loaded via `rx.script(src="/wallet_bridge.js")` from `head_components` in `reflex_app/aequitas_rx/aequitas_rx.py`. Uses `window.ethereum` for wallet plumbing and lazily loads `ethers@6.13.2` from a CDN for contract calls.

Responsibility split:
- **Python engine = truth** (actuarial calculations).
- **Solidity contracts = execution + governance enforcement + audit trail**.
- **Reflex UI = presentation and orchestration**.
- **MetaMask / wallet bridge = signing**.

## 3. What is already working

All items verified either by `python3 /tmp/pytest_shim.py tests/` (116 tests passing) or by direct inspection of the committed files.

- The seven existing Reflex pages render: Overview (KPI strip + fund projection), Members (roster + drilldown), Fairness (governance sandbox + Monte Carlo stress), Digital Twin (`/twin`, time-evolving population/fund/fairness with 6 scenario presets), Operations (hash-chained event feed), Contracts (on-chain action cards with bridged payloads), How It Works (8-step lifecycle + contract crosswalk).
- The Python actuarial engine is complete and tested: 116/116 Python tests pass, including new tests for `engine.onchain_registry` (23 new tests) and the contract-map-real-function guard in `tests/test_events.py`.
- The digital twin simulator runs all 6 scenario presets (stable, market_crash, inflation_shock, aging_society, unfair_reform, young_stress) with 1000 members × 30 years × 200 stress scenarios.
- The deployment-registry fallback chain works: `engine.onchain_registry.load_any_deployment()` returns the populated local-Anvil deployment from `latest.txt` if `sepolia.json` is empty, and returns the Sepolia registry as soon as `sepolia.json` is populated.
- The navbar link and route wiring for `/actions` are in place: `aequitas_rx.py` registers the page with `AppState.refresh_view` on load; `components.py::navbar()` shows the Actions link and wallet badge.
- The `rx.script(src="/wallet_bridge.js")` head component is wired in `aequitas_rx.py`.
- The Actions page at `/actions` renders the role grid (Governance, Actuary, Treasury, Auditor), the protocol status banner, the deployment registry block, and the confirmation drawer.
- The confirmation drawer correctly distinguishes LIVE vs BRIDGED actions, shows a reversibility ribbon, and collapses technical details behind an accordion.
- The audit chain records `wallet_connected`, `action_confirmed`, `tx_submitted`, `tx_failed` into the existing `_EVENT_LOG`, which surfaces through the Operations feed.
- Etherscan URL builders (`etherscan_address`, `etherscan_tx`) return correct Sepolia deep-links.

## 4. What is partially implemented

- **`contracts/deployments/sepolia.json`** has the Sepolia header committed (`chain_id: 11155111`, `explorer_base: …`) but `contracts: {}`. The deploy addresses from the already-live Sepolia deployment have not been copied in. Until this is populated, the UI correctly shows "NOT DEPLOYED" for Sepolia — which is the UI behaving correctly against an incomplete registry, not a bug.
- **Live on-chain actions** use fixed demo arguments embedded in `assets/wallet_bridge.js::DEMO_ARGS`. They will call the correct contract function with the signer's wallet, but the arg values (two-cohort stub, 0.01 ETH deposit, placeholder retiree address `0x0…01`) are illustrative rather than driven by `AppState`. For a genuine demo they will sign and emit real events; they will not reflect the state visible on other pages.
- **Transaction lifecycle**: the bridge returns immediately on `tx.hash` and writes `last_tx_status = "pending"`. There is no `provider.waitForTransaction(hash)` call, so the pill stays **PENDING** even after the block is mined. The user must click the Etherscan link to see confirmation. This is a deliberate stop for now.
- **Wallet-change listeners**: `wallet_bridge.js::connect()` subscribes to `accountsChanged` and `chainChanged`, but only `console.log`s the events. They are not propagated back into `AppState`, so if the user switches account or network in MetaMask after connecting, the Reflex banner becomes stale until the next button click.
- **Deployment verification status**: the `verified` boolean in `sepolia.json` is read and rendered as a pill. There is no runtime verification against Etherscan's API — Codex would need to add that if a live check is required.
- **Deploy + DemoFlow actions** are BRIDGED: the confirmation drawer acknowledges the action and logs `action_confirmed`, but does not execute the `forge script` command. The user still has to paste the command into a terminal. This is intentional — deploys should not sign from a wallet UI — but the UX copy could make that clearer.
- **Provider detection**: `wallet_bridge.js::hasEthereum()` only checks `window.ethereum`. It does not use EIP-6963 provider discovery, which means Brave's built-in wallet can shadow MetaMask if both are installed, and multi-provider setups default to whichever wallet injected last.

## 5. What is currently broken

### 5a. "Connect wallet does nothing"

- **Symptom**: clicking the Connect MetaMask button (either the navbar badge or the `connect_prompt` banner on `/actions`) does not open MetaMask and does not visibly update state. In the worst case the click appears inert with no console output.
- **Likely causes, in descending order of probability**:
  1. **Script-load order race.** `rx.script(src="/wallet_bridge.js")` is inserted via `head_components`. If `window.aequitasWallet` is not yet defined when the user clicks, the JS expression `window.aequitasWallet && window.aequitasWallet.connect()` short-circuits to `undefined` / `false`. Reflex passes that to `AppState.on_wallet_connected`, which coerces it to `{"ok": False, "error": "Unexpected wallet response"}`. No MetaMask popup, and the error message is written to `wallet_last_error` but nothing on screen surfaces it prominently. This is the single most likely root cause.
  2. **Reflex version vs `head_components` shape.** In some Reflex versions, `head_components=[rx.script(src=...)]` on `rx.App(...)` is ignored silently. The alternative is to add the script per-page as a child of the page body, or to use `app.head_components` assignment after construction, or to use `rx.script` inline on the page root. Uncertain which Reflex version the repo is on — Codex should check `reflex.__version__` and adjust.
  3. **Provider collision with Brave.** Brave's built-in wallet injects `window.ethereum` before MetaMask does. In Brave, `eth_requestAccounts` on the default provider opens Brave Wallet, not MetaMask. User reports "nothing happens" can mean a second (hidden) provider window.
  4. **`rx.call_script` async/await semantics.** The JS expression is a promise call. Older Reflex versions of `call_script` did not await the returned promise — they passed the Promise object as a raw value. If that is this repo's version, the callback fires immediately with a non-resolved Promise reference and `on_wallet_connected` never sees `ok: true`.
  5. **Asset not served at `/wallet_bridge.js`.** Reflex serves the `assets/` directory at root only after an initial build. If `reflex run` was launched before the file was created, the dev server may need a restart. Check the browser devtools Network tab for `wallet_bridge.js` returning 200.
- **Where to look first**:
  1. `reflex_app/aequitas_rx/assets/wallet_bridge.js` — top of the file logs `"[aequitas] wallet bridge loaded · MetaMask: detected/missing"` to the browser console. If this line is absent from the browser console, the script did not load. If it says `missing`, `window.ethereum` is not present at the time of load.
  2. `reflex_app/aequitas_rx/aequitas_rx.py` — check that `head_components=[rx.script(src="/wallet_bridge.js")]` is present on the `rx.App(...)` constructor. Compare against a working Reflex example in the installed version's own docs.
  3. `reflex_app/aequitas_rx/state.py::AppState.connect_wallet` — confirm the call is `return rx.call_script(..., callback=AppState.on_wallet_connected)`. The return is required for Reflex to dispatch the event.
  4. Browser devtools → Network → filter `wallet_bridge.js`. If 404, the asset path is wrong. If 200 but no `window.aequitasWallet`, the script errored at parse time.

### 5b. "Actions page still confusing for non-technical users"

- **Symptom**: the Actions page renders but a non-technical juror does not understand what "BRIDGED · CLI" means, does not see that the deploy runbook is a shell task, and does not get a clear "you are ready / not ready" signal.
- **Likely causes**:
  1. The deploy runbook (`_deploy_runbook()` in `pages/actions.py`) is shown to everyone by default, not only when `registry_present` is false.
  2. The mode pill uses the string "BRIDGED · CLI" which is jargon. A non-technical reader does not know what bridged means.
  3. The four role columns are all rendered at equal weight. There is no "start here" affordance.
  4. The confirmation drawer says "You are about to trigger a change that may be written to the audit chain" — the "may be" is weaker than "will be" and adds doubt.
- **Where to look first**: `reflex_app/aequitas_rx/pages/actions.py` (page composition, role grid ordering, runbook visibility), `reflex_app/aequitas_rx/components_wallet.py` (mode pill labels, drawer copy, blocker text).

### 5c. "Deployment status / verification / live-vs-local messaging inconsistent"

- **Symptom**: the UI shows two different deployment signals that can disagree: the legacy `deployment_ribbon()` component (reads `latest.txt` via `engine.deployments.load_latest`) and the new Actions-page `protocol_status_banner()` (reads `sepolia.json` via `engine.onchain_registry.load_any_deployment`). After a real Sepolia deploy, if the user populates `sepolia.json` but not `latest.txt` (or vice versa), the two banners tell different stories.
- **Likely cause**: the two loaders were added incrementally and the legacy ribbon was preserved to avoid a destructive refactor.
- **Where to look first**: `reflex_app/aequitas_rx/components.py::deployment_ribbon()` (shows a message based on `AppState.deployment_detected`), `reflex_app/aequitas_rx/state.py::_refresh()` (calls both `load_latest()` and `self._refresh_registry()` — the two paths write to `deployment_*` and `registry_*` independently).

### 5d. Missing JS bridge wiring for chain + account change events

- **Symptom**: after connecting, if the user switches account or network inside MetaMask, the navbar badge and status banner do not update until the next click.
- **Likely cause**: the bridge subscribes in `connect()` but only logs. There is no call back into Reflex when chain/account changes.
- **Where to look first**: `reflex_app/aequitas_rx/assets/wallet_bridge.js` — the `connect()` function's `window.ethereum.on("chainChanged", ...)` and `accountsChanged` handlers.

### 5e. Sepolia registry is empty while the live deployment exists

- **Symptom**: the user reports a live Sepolia deployment, but the UI reads "NOT DEPLOYED" in the banner and the registry block shows no contract rows.
- **Likely cause**: `contracts/deployments/sepolia.json` has `"contracts": {}`. The Foundry broadcast log at `contracts/broadcast/Deploy.s.sol/11155111/run-latest.json` presumably has the 8 addresses but has not been transcribed into the registry.
- **Where to look first**: `contracts/broadcast/Deploy.s.sol/11155111/run-latest.json` (if present) and `contracts/deployments/sepolia.json`. The schema to follow is `contracts/deployments/sepolia.schema.md`.

## 6. Files Codex should inspect first

1. `reflex_app/aequitas_rx/aequitas_rx.py` — the app entry. Confirms route registrations and the `head_components=[rx.script(src="/wallet_bridge.js")]` line.
2. `reflex_app/aequitas_rx/assets/wallet_bridge.js` — the entire browser wallet layer lives here. `connect()`, `switchToSepolia()`, `runAction()`, `DEMO_ARGS`, `ABI`.
3. `reflex_app/aequitas_rx/state.py` — especially the "Wallet / on-chain handlers" section (`connect_wallet`, `on_wallet_connected`, `switch_to_sepolia`, `on_chain_changed`, `disconnect_wallet`, `open_action`, `close_action`, `confirm_action`, `on_tx_submitted`, `clear_last_tx`) and the `_refresh_registry()` internal. Also the `_ACTIONS: ClassVar[dict[str, dict]]` catalogue.
4. `reflex_app/aequitas_rx/components_wallet.py` — `wallet_badge`, `protocol_status_banner`, `confirm_drawer`, `action_card_v2`, `role_column`, `connect_prompt`.
5. `reflex_app/aequitas_rx/pages/actions.py` — the Operator Action Center page composition, role grid, deploy runbook block, registry block.
6. `engine/onchain_registry.py` — `load_registry()`, `load_any_deployment()`, `OnchainRegistry`, `ContractRecord`, Etherscan URL builders, `SEPOLIA_CHAIN_ID = 11155111`.
7. `contracts/deployments/sepolia.json` — the registry file. Currently header-only.
8. `contracts/deployments/sepolia.schema.md` — the schema + three-step populate runbook.
9. `engine/deployments.py` — legacy `latest.txt` loader still used by the existing `deployment_ribbon()`.
10. `reflex_app/aequitas_rx/components.py` — `navbar()` (Actions link + wallet badge), `deployment_ribbon()` (legacy status strip), `shell()`.
11. `contracts/src/FairnessGate.sol`, `StressOracle.sol`, `BackstopVault.sol`, `VestaRouter.sol` — the four contracts targeted by live actions. Function signatures must match the ABI fragments in `wallet_bridge.js::ABI`.
12. `contracts/script/Deploy.s.sol` — what `sepolia.json` needs to be reconciled against.
13. `tests/test_onchain_registry.py`, `tests/test_events.py` — the registry-shape + contract-map-real-function invariants.
14. `run_app.py` — the actual app entry for `python run_app.py` or `reflex run`.
15. `contracts/foundry.toml` and `contracts/.env.example` — RPC / etherscan configuration.

## 7. Files changed recently

- `engine/onchain_registry.py` — new. Network constants, `OnchainRegistry` dataclass, `load_registry`, `load_any_deployment`, URL builders.
- `contracts/deployments/sepolia.json` — new. Committed header-only registry for Sepolia (chain_id set, contracts empty).
- `contracts/deployments/sepolia.schema.md` — new. Schema documentation + deploy runbook.
- `reflex_app/aequitas_rx/assets/wallet_bridge.js` — new. Browser-side MetaMask + ethers.js bridge with minimal ABIs for 6 live actions and demo argument packs.
- `reflex_app/aequitas_rx/components_wallet.py` — new. Wallet badge, protocol status banner, confirm drawer, `action_card_v2`, `role_column`, `connect_prompt`.
- `reflex_app/aequitas_rx/pages/actions.py` — new. Operator Action Center at `/actions`.
- `reflex_app/aequitas_rx/state.py` — modified additively: ~40 wallet/registry/tx/confirm fields, 9 new event handlers, `_ACTIONS: ClassVar` catalogue, `_refresh_registry()` internal, 10 new `@rx.var` computed vars.
- `reflex_app/aequitas_rx/components.py` — modified: `navbar()` now includes the Actions link and the `wallet_badge()` slot (late-imported to avoid a circular dependency).
- `reflex_app/aequitas_rx/aequitas_rx.py` — modified: added `/actions` route, added `head_components=[rx.script(src="/wallet_bridge.js")]` on `rx.App(...)`.
- `tests/test_onchain_registry.py` — new. 23 tests covering network constants, Etherscan URL builders, JSON parsing of `sepolia.json`, and the JSON-vs-`latest.txt` fallback chain. Written against the minimal pytest shim (no fixtures).

## 8. Current Sepolia / deployment context

- The user states that the 8 Aequitas contracts are already deployed on Sepolia. Codex should treat the live deployment as a fact and only populate the registry to reflect it — not redeploy.
- The user has a Sepolia RPC URL locally (in a local `.env`, not in the repo).
- The user has an Etherscan API key locally.
- The user has a MetaMask wallet funded with Sepolia ETH.
- The UI must never ask for a private key. All signing flows through MetaMask via `window.aequitasWallet.runAction(...)` which resolves `ethers.BrowserProvider(window.ethereum).getSigner()` and uses that signer to send the transaction. The Reflex server-side code only constructs the JS call string and reads back the tx hash.
- For a non-technical user, the expected app behaviour is:
  1. They land on `/`. They see the scheme KPIs.
  2. They navigate to `/actions`. They see a top banner stating "Wallet not connected · Sepolia · 8 contracts deployed · verified".
  3. They click **Connect wallet**. MetaMask opens. They approve.
  4. The banner turns green. The navbar badge shows their short address + `SEPOLIA` pill.
  5. They click any card in the role grid. A confirmation drawer explains what the action does in plain English, shows the contract name and reversibility, and exposes the raw payload only behind an "Advanced" accordion.
  6. They click **Sign in MetaMask**. MetaMask opens. They approve.
  7. The last-action tile flips to PENDING and exposes an **Etherscan** link.
  8. They never see a terminal command, private key, ABI, calldata, or gas field by default.

## 9. Immediate next task for Codex

**Fix wallet connection on `/actions` so clicking "Connect wallet" reliably opens MetaMask, the navbar badge updates visibly, and the Sepolia-switch flow is one button press away.**

Scope of that single task:

1. Verify `reflex_app/aequitas_rx/assets/wallet_bridge.js` is served at `/wallet_bridge.js` on `reflex run`. Open browser devtools → Network. If 404, fix by: either moving the script to the correct assets directory for the installed Reflex version, or switching from `rx.script(src=...)` in `head_components` to `rx.script(open_file("assets/wallet_bridge.js").read())` inline on the page root of `actions_page()`.
2. Replace `rx.call_script("window.aequitasWallet && window.aequitasWallet.connect()", ...)` with a defensive script string that waits for the bridge to be ready. Concrete implementation: change the JS to a self-contained IIFE that awaits a small retry loop: `"await (async () => { for (let i=0; i<40; i++) { if (window.aequitasWallet) return await window.aequitasWallet.connect(); await new Promise(r => setTimeout(r, 50)); } return { ok:false, error:'wallet bridge failed to load' }; })()"`. Same pattern for `switch_to_sepolia` and `runAction`.
3. Add EIP-6963 provider discovery in `wallet_bridge.js` so MetaMask is selected even when Brave Wallet or Coinbase Wallet also injects `window.ethereum`. Listen for `eip6963:announceProvider` events, pick the provider whose `info.rdns` is `io.metamask`, and fall back to `window.ethereum` if none announce. Expose the chosen provider as `window.aequitasWallet._provider` for debugging.
4. Propagate `chainChanged` and `accountsChanged` back into Reflex. Concrete: in `connect()` inside `wallet_bridge.js`, subscribe the events to a shared handler that dispatches a `CustomEvent("aequitas:wallet", { detail })` on `window`. In Reflex, use a `rx.script` that listens on window for `aequitas:wallet` and calls `AppState.on_wallet_connected` / `AppState.on_chain_changed` via the Reflex event dispatcher. If inline dispatch is not supported in the installed Reflex version, fall back to a polling `rx.call_script` on an interval timer.
5. Surface `AppState.wallet_last_error` visibly. Currently it is stored but not rendered. Add a small warn-pill line to the `connect_prompt()` component in `components_wallet.py` that renders `rx.cond(AppState.wallet_last_error != "", rx.text(AppState.wallet_last_error, ...), rx.fragment())` so failed connections are not silent.
6. Hide the deploy runbook block by default (wrap `_deploy_runbook()` in `rx.cond(~AppState.registry_present, ..., rx.fragment())`) so a non-technical user does not see shell instructions once Sepolia is wired up.
7. Populate `contracts/deployments/sepolia.json` from `contracts/broadcast/Deploy.s.sol/11155111/run-latest.json`. Codex can either write a small Python helper (`scripts/import_broadcast.py`) that reads the broadcast JSON and emits the registry JSON, or ask the user to paste the 8 addresses in. Prefer the helper — it is deterministic and removes the manual step from the demo.

Explicitly do **not**:
- Redeploy the contracts.
- Rewrite `state.py`, `engine/`, or any existing pages.
- Add new dependencies beyond what the repo already uses. `ethers` is loaded from a CDN inside `wallet_bridge.js` and that is sufficient.
- Introduce a second wallet library (wagmi, web3modal, rainbowkit).

## 10. Acceptance criteria

- [ ] **Connect wallet opens MetaMask.** Clicking either the navbar badge or the `connect_prompt` button on `/actions` opens the MetaMask extension popup within one second on a machine with MetaMask installed. Brave users with Brave Wallet installed alongside MetaMask also see the MetaMask popup, not the Brave Wallet.
- [ ] **Wallet status updates visibly.** After approving in MetaMask, the navbar badge flips from "Connect wallet" to a chip showing the 0x-abcd…1234 short address and a green `SEPOLIA` pill. The `protocol_status_banner()` Wallet tile reads "Connected to Sepolia" within one second.
- [ ] **Wrong network is caught and fixable.** If the user is on Mainnet or any non-Sepolia network when they connect, the badge shows an amber `WRONG NETWORK` pill, the Wallet tile sub-text says "Switch to Sepolia", and clicking the visible **Switch to Sepolia** button triggers `wallet_switchEthereumChain` in MetaMask. If Sepolia is not yet added to MetaMask, the `wallet_addEthereumChain` fallback in `wallet_bridge.js::switchToSepolia` kicks in.
- [ ] **Existing deployment is recognised automatically.** With a populated `contracts/deployments/sepolia.json`, the Deployment tile on the status banner shows `VERIFIED · SEPOLIA` or `ON SEPOLIA`, the registry block on `/actions` lists all 8 contracts with Etherscan deep-links, and the deploy runbook is hidden.
- [ ] **Live vs bridged separation is obvious.** Live actions (Governance, Actuary, Treasury columns) show a green `LIVE` pill. Bridged actions (Auditor column) show a neutral `BRIDGED` pill. Non-technical copy on the confirmation drawer explains that bridged actions happen in a terminal, not via MetaMask. The word "CLI" does not appear on any card by default.
- [ ] **Confirmation drawer is jury-safe.** The drawer opens on card click, shows the action label, the plain-English summary, the Actuarial meaning, the Protocol meaning, and a REVERSIBILITY ribbon. The "Advanced · technical details" accordion is collapsed by default and contains the contract, function, parameter rows, and deployed address.
- [ ] **Live signing round-trips.** After Connect + Sepolia + a populated registry, clicking one live action (e.g. Publish fairness stress result), confirming, and signing in MetaMask results in `AppState.last_tx_status == "pending"` with a valid tx hash and an Etherscan link that opens the correct Sepolia tx page. The Operations feed gets a new `tx_submitted` entry.
- [ ] **No shell-oriented instructions visible by default.** On a machine with Sepolia registry populated and wallet connected, the `/actions` page contains no `forge`, `cast`, `$SEPOLIA_RPC_URL`, or `.env` references. Those references are reachable only by expanding the Advanced accordion or by being in the pre-deployment state.
- [ ] **All existing tests still pass.** `python3 /tmp/pytest_shim.py tests/` returns 116 passed, 0 failed (or more if Codex adds new tests — none must be removed).
- [ ] **Python files still import cleanly.** `python3 -m py_compile` on every `.py` file under `reflex_app/aequitas_rx/` and `engine/` returns zero exit code.

## 11. Exact run/test instructions

All commands assume the repo root is `/Users/tarafimohammedyazid/Documents/Claude/Projects/aequitas` (Codex's working directory).

- Run the Python test suite (no pytest installation required — the repo targets a minimal shim):

  ```
  python3 /tmp/pytest_shim.py tests/
  ```

  Expected tail: `116 passed, 0 failed`. If `/tmp/pytest_shim.py` is absent on Codex's machine, substitute `pytest tests/` once `pytest` is installed (`pip install pytest`).

- Syntax-check every modified Python file:

  ```
  python3 -m py_compile \
      engine/onchain_registry.py \
      reflex_app/aequitas_rx/state.py \
      reflex_app/aequitas_rx/components.py \
      reflex_app/aequitas_rx/components_wallet.py \
      reflex_app/aequitas_rx/aequitas_rx.py \
      reflex_app/aequitas_rx/pages/actions.py
  ```

- Run the Reflex app locally:

  ```
  cd reflex_app
  reflex run
  ```

  Frontend defaults to `http://localhost:3000`. Backend to `http://localhost:8000`. If Reflex is not yet initialised in that directory, run `reflex init` first.

- Compile Solidity and run Foundry tests:

  ```
  cd contracts
  forge build
  forge test -vv
  ```

- Populate `contracts/deployments/sepolia.json` from an existing broadcast log (if the script does not yet exist, Codex should create it as part of the next task):

  ```
  python3 scripts/import_broadcast.py \
      contracts/broadcast/Deploy.s.sol/11155111/run-latest.json \
      contracts/deployments/sepolia.json
  ```

- Verify the registry loads as expected:

  ```
  python3 -c "from engine.onchain_registry import load_any_deployment; r = load_any_deployment(); print(r.chain_id, len(r.contracts))"
  ```

  After populating Sepolia: expect `11155111 8`.

## 12. Risks / gotchas

- **Reflex version sensitivity.** `rx.call_script(..., callback=EventHandler)` and `head_components=[rx.script(...)]` have both shifted across Reflex minor releases. Pin the version before debugging. If `reflex --version` reports anything below 0.6, the callback semantics are different and the connect flow will behave inertly.
- **`rx.fragment()` with dynamic children.** Mixing literal strings and `Var` children inside `rx.fragment()` or `rx.text()` is a common Reflex pitfall. All dynamic text in this codebase is kept as its own `rx.text(...)` node. Codex should follow that pattern.
- **`AppState` is a module-level singleton.** `_LEDGER` and `_EVENT_LOG` at the top of `state.py` are globals shared across all browser sessions. That is deliberate for a single-operator demo. For a multi-user deploy, those need to move per-session.
- **The `_ACTIONS` dict must remain `ClassVar`.** Reflex treats class-level mutable attributes as state vars unless annotated `ClassVar`. If Codex adds another constant table, annotate it the same way.
- **`f"{AppState.var}"` does not work.** `AppState` fields are Reflex `Var`s, not Python strings. String interpolation must go through separate `rx.text(...)` children or `rx.Var` concatenation. The Actions page was rewritten once already to fix this.
- **`on_click=lambda: AppState.open_action(key)` does not work.** Use the `EventSpec` form: `on_click=AppState.open_action(key)`. The Actions page `action_card_v2` uses the correct form.
- **The wallet bridge uses `rx.script(src="/wallet_bridge.js")` absolute path.** If the app is ever mounted under a sub-path or behind a reverse proxy, that path will 404. Switch to a Reflex-aware helper (`rx.asset("wallet_bridge.js")` if available) or a relative reference.
- **Minimal ABIs in `wallet_bridge.js::ABI` are hand-maintained.** A Solidity function rename will not break the build. The existing `tests/test_events.py::test_contract_map_names_real_solidity_functions` guards the Python-side `CONTRACT_MAP` but not the JS ABIs. Codex should add a parallel test that greps the JS file against `contracts/src/*.sol`.
- **`DEMO_ARGS` in `wallet_bridge.js` uses placeholder addresses.** The `open_retirement` action signs `0x0000000000000000000000000000000000000001` as the retiree. The transaction will succeed but does not reflect real scheme state.
- **ContractRecord address casing is preserved from the registry file.** Etherscan links use the exact casing stored. If the user pastes lowercased addresses, the Etherscan page still resolves but the UI copy loses EIP-55 checksum presentation.
- **Nothing caches the Sepolia registry across requests.** Every `AppState.refresh_view` re-reads `sepolia.json` from disk. That is fine for local dev but becomes an I/O hot spot if deployed at scale.
- **Uncertain**: whether MetaMask popups fire reliably on `rx.call_script(...)` in Firefox. All the flows were designed against Chromium-based browsers (Chrome + Brave + Edge). Codex should verify on whatever browser the jury will use.
- **Uncertain**: whether `head_components` is a supported field in the installed Reflex version. If not, the fix is to inject the script inline on the page root (`actions_page()` returns an `rx.box(rx.script(src=...), ...)`). That is a one-line change.
- **Uncertain**: whether `ethers` 6.13.2 on the cdnjs CDN URL used in `wallet_bridge.js` is still cache-warm. If the CDN returns 404, wallet_bridge.js will fail to load ethers and `runAction` will error out with "failed to load ethers.js from CDN". `connect()` and `switchToSepolia()` do not depend on ethers and will keep working.

## 13. Codex starter prompt

```
You are continuing work on the Aequitas repository at
/Users/tarafimohammedyazid/Documents/Claude/Projects/aequitas.

Do not restart from zero. The repo already has:
- a complete Python actuarial engine under engine/
- 8 deployed Solidity contracts on Sepolia under contracts/src/
- a Reflex frontend under reflex_app/aequitas_rx/ with 8 pages
  including a new Operator Action Center at /actions
- a wallet bridge at reflex_app/aequitas_rx/assets/wallet_bridge.js
  that exposes window.aequitasWallet.{connect, switchToSepolia, runAction}
- a deployment registry at contracts/deployments/sepolia.json
  (currently header-only — contracts block is empty)
- 116 passing Python tests including tests/test_onchain_registry.py

Read CODEX_HANDOFF.md at the repo root before making any changes.

Your immediate task is to make wallet connection work reliably and make
the /actions page usable by a non-technical jury member. Scope:

1. Debug the "Connect wallet does nothing" failure on /actions. Start
   with the browser devtools Network tab to confirm /wallet_bridge.js
   loads, then the console to confirm the "[aequitas] wallet bridge
   loaded" breadcrumb appears. If either is missing, fix how the script
   is mounted in reflex_app/aequitas_rx/aequitas_rx.py.
2. Harden rx.call_script dispatches so they wait for
   window.aequitasWallet to be defined before invoking connect() /
   switchToSepolia() / runAction(). Use the retry-loop pattern described
   in section 9 of CODEX_HANDOFF.md.
3. Add EIP-6963 provider discovery inside wallet_bridge.js so MetaMask
   is selected even when Brave Wallet is also installed.
4. Propagate MetaMask chainChanged and accountsChanged back into
   AppState so the navbar badge and status banner stay live after a
   user switches account or network in the wallet.
5. Render AppState.wallet_last_error visibly inside connect_prompt() in
   components_wallet.py so failed connections are not silent.
6. Hide the deploy runbook on /actions when registry_present is true
   (wrap it in rx.cond).
7. Write scripts/import_broadcast.py that parses
   contracts/broadcast/Deploy.s.sol/11155111/run-latest.json and emits
   the fully-populated contracts/deployments/sepolia.json per the schema
   in contracts/deployments/sepolia.schema.md. Run it against the user's
   existing Sepolia broadcast log.

Constraints:
- Do not redeploy the Solidity contracts.
- Do not rewrite engine/ or any existing Reflex page besides actions.py,
  state.py, components.py, components_wallet.py.
- Do not add new Python or JS dependencies beyond the ethers CDN already
  used by wallet_bridge.js.
- Preserve all 116 passing Python tests. Add new tests for any new
  Python code you write (e.g. scripts/import_broadcast.py).

Finish when every checkbox in section 10 of CODEX_HANDOFF.md is green,
then run:
  python3 /tmp/pytest_shim.py tests/
  python3 -m py_compile $(git ls-files '*.py')
  cd reflex_app && reflex run
and manually verify the Connect wallet → Sepolia → Publish stress round
trip against the live deployment.
```
