# Aequitas Codex Handoff

Target repo: `/Users/tarafimohammedyazid/Documents/Claude/Projects/aequitas`
Last test baseline: 134 Python tests pass under `/tmp/pytest_shim.py`; all Python files under `engine/`, `reflex_app/aequitas_rx/`, `scripts/` compile cleanly with `python3 -m py_compile`. Solidity not re-built in this session.

## 1. Project goal

Aequitas is a hybrid actuarial + blockchain protocol for a defined-benefit pension scheme. A Python actuarial engine produces all economics (EPV, per-cohort money-worth ratio, fairness corridor, stochastic stress, 30-year digital twin); eight Solidity contracts record the verdicts on-chain for audit. The product vision is a jury-ready Reflex web app at `/actions` where a non-technical operator connects MetaMask on Sepolia, signs a handful of clearly-labelled actions, and sees every result reflected in plain English plus a linkable Etherscan receipt — never touching a CLI, a private key, or calldata by default.

## 2. Current architecture

- **Python actuarial engine** (`engine/`). Source of truth for every number in the UI. No blockchain dependency. Key modules: `actuarial.py`, `ledger.py`, `projection.py`, `fairness.py`, `fairness_stress.py`, `system_simulation.py`, `population.py`, `scenarios.py`, `events.py`, `models.py`. Chain-adjacent but still pure Python: `chain_bridge.py` (Python→Solidity call encoders, no web3), `chain_stub.py` (tamper-evident in-memory `EventLog`).
- **Deployment registry readers** (`engine/deployments.py` + `engine/onchain_registry.py`). `load_latest()` parses the legacy `contracts/deployments/latest.txt` key=value file (local Anvil). `load_registry()` parses the richer `contracts/deployments/sepolia.json`. `load_any_deployment()` is the single entry point Reflex calls: it prefers the JSON registry and falls back to the legacy file.
- **Reflex frontend** (`reflex_app/aequitas_rx/`). Server-rendered Python UI. Eight routes registered in `aequitas_rx.py`: `/`, `/members`, `/fairness`, `/twin`, `/actions`, `/operations`, `/contracts`, `/how`. All state in one class `AppState` at `state.py` (1,714 lines). The Reflex server never holds a private key.
- **Solidity contracts** (`contracts/src/`): `CohortLedger.sol`, `FairnessGate.sol`, `MortalityOracle.sol`, `LongevaPool.sol`, `BenefitStreamer.sol`, `VestaRouter.sol`, `StressOracle.sol`, `BackstopVault.sol`. Foundry toolchain. `Deploy.s.sol` and `DemoFlow.s.sol` under `contracts/script/`. `contracts/foundry.toml` defines the `sepolia` RPC endpoint and etherscan key from env.
- **Sepolia deployment** is live. Addresses are in `contracts/broadcast/Deploy.s.sol/11155111/run-latest.json` (Foundry broadcast log) AND have been mirrored into `contracts/deployments/sepolia.json` by `scripts/import_broadcast.py`. The deployer EOA was `0xa275c7e279fb51f419db50244eba5f0f0197e9e0`.
- **MetaMask / browser wallet layer** (`reflex_app/aequitas_rx/assets/wallet_bridge.js`, 412 lines). Exposes `window.aequitasWallet.{connect, switchToSepolia, runAction, hasEthereum, getState}`. Served by Reflex at `/wallet_bridge.js` and loaded via `head_components=[rx.script(src="/wallet_bridge.js")]` on the `rx.App(...)` constructor. Uses EIP-6963 for provider discovery (prefers `io.metamask`), falls back to `window.ethereum`. `ethers@6.13.2` is lazy-loaded from `cdnjs.cloudflare.com` only when a live action is dispatched.

Responsibility split:

- **Python engine = truth.** Every actuarial metric.
- **Solidity contracts = execution + irrevocable audit trail.**
- **Reflex UI = presentation + orchestration only.**
- **MetaMask / wallet bridge = signing.**

## 3. What is already working

Verified by running `python3 /tmp/pytest_shim.py tests/` (134 passed, 0 failed) and direct file inspection.

- All eight Reflex pages render against the existing `AppState`: Overview, Members, Fairness, Digital Twin, Operations, Contracts, How It Works, Actions. The navbar (`components.py::navbar`) has a link to each and a wallet chip slot on the right.
- The Python actuarial engine is complete and covered: 134/134 tests pass across 14 suites (`test_actuarial`, `test_chain_bridge`, `test_chain_stub`, `test_deployments`, `test_events`, `test_fairness`, `test_fairness_stress`, `test_import_broadcast`, `test_ledger`, `test_onchain_registry`, `test_population`, `test_projection`, `test_scenarios`, `test_system_simulation`).
- The digital twin simulator (`engine.system_simulation.run_system_simulation`) runs all six scenario presets (`stable`, `market_crash`, `inflation_shock`, `aging_society`, `unfair_reform`, `young_stress`) with 1,000 members × up to 30 years × 200 stress scenarios.
- `engine.onchain_registry.load_any_deployment()` returns a `OnchainRegistry` with `chain_id=11155111`, 8 contracts, `verified=True` against the currently-committed `contracts/deployments/sepolia.json`.
- `scripts/import_broadcast.py` is implemented and regenerates `contracts/deployments/sepolia.json` from the Foundry broadcast log. It has 18 pinning tests in `tests/test_import_broadcast.py`. CLI flags: `--chain-id`, `--verified` (list or `all`), `--dry-run`.
- `reflex_app/aequitas_rx/assets/wallet_bridge.js` is implemented: EIP-6963 discovery, `connect()`, `switchToSepolia()` (with `wallet_addEthereumChain` fallback for error 4902), `runAction()`, `getState()`, event subscriptions for `chainChanged` and `accountsChanged` that re-emit via a `CustomEvent("aequitas:wallet", …)` on `window`.
- The Reflex↔JS event bridge is in place (`components_wallet.py::wallet_event_bridge`). A hidden button with `id="__aequitas_refresh_wallet"` is clicked by an installed `aequitas:wallet` window listener; its `on_click` calls `AppState.refresh_wallet_state` which in turn runs `window.aequitasWallet.getState()` and reconciles `wallet_*` state fields.
- `AppState._bridge_call(body)` (static helper in `state.py`) wraps every `rx.call_script` in a 40 × 50 ms retry IIFE that waits for `window.aequitasWallet` to exist before invoking the promise, so the first click on a cold page no longer silently resolves to `undefined`.
- `components_wallet.py::_wallet_error_strip()` renders `AppState.wallet_last_error` as a red ribbon with a **Retry** button whenever it's non-empty. It leads `connect_prompt()`.
- `pages/actions.py::_deploy_runbook` is wrapped in `rx.cond(~AppState.registry_present, …, rx.fragment())`, so the shell runbook disappears as soon as `sepolia.json` is populated.
- The confirmation drawer (`components_wallet.py::confirm_drawer`) distinguishes `LIVE · ON-CHAIN` vs `BRIDGED · CLI`, shows Actuarial meaning / Protocol meaning side-by-side, a REVERSIBILITY ribbon, a collapsed "Advanced · technical details" accordion containing parameter rows and the on-chain target address, and a BLOCKED ribbon that surfaces `AppState.live_action_blocker` when the action can't run (wallet missing, wrong network, registry empty).
- The audit chain (`engine.chain_stub.EventLog`, the singleton `_EVENT_LOG` in `state.py`) records `wallet_connected`, `action_confirmed`, `tx_submitted`, `tx_failed`, `twin_simulation_run`, `fairness_stress_run`, `proposal_evaluated`, `demo_data_loaded`, and the other lifecycle events. The Operations page streams them into a hash-chained feed.
- Etherscan deep-links work: `etherscan_address(11155111, addr)` and `etherscan_tx(11155111, hash)` return URLs rooted at `https://sepolia.etherscan.io`. They're bound to `registry_rows[*].explorer_url`, `registry_explorer_deployer_url`, `wallet_explorer_url`, and `last_tx_explorer_url`.

## 4. What is partially implemented

- **Live-action arguments are still demo fixtures.** `wallet_bridge.js::DEMO_ARGS` hard-codes a two-cohort stub for `publish_baseline`/`submit_proposal`, `level=75` for `publish_stress`, `0.01 ETH` for `fund_reserve`, `0.005 ETH` for `release_reserve`, and retiree address `0x0000…0001` for `open_retirement`. Transactions sign and emit real events on Sepolia, but the numbers don't reflect anything the user sees on `/fairness` or `/members`.
- **Transaction confirmation is not awaited.** `wallet_bridge.js::runAction` returns `{ok:true, hash, confirmed:false}` as soon as MetaMask accepts. `on_tx_submitted` writes `last_tx_status="pending"`. There is no `provider.waitForTransaction(hash)`. The pill stays PENDING until the user refreshes or the bridge gets a `chainChanged` event. Etherscan link is the intended path to see confirmation.
- **`verified` flag is trusted from the registry file.** No runtime check against the Etherscan verification API. If the UI says `VERIFIED · SEPOLIA`, it's because `sepolia.json` said so.
- **BRIDGED actions (`deploy_protocol`, `demo_flow`) are acknowledgement-only.** `AppState.confirm_action` logs `action_confirmed` and flips the tile to CONFIRMED without executing anything. The drawer copy tells the user to run the command themselves. This is deliberate — a Reflex UI should not shell out to `forge` — but the copy could be blunter.
- **Two deployment banners can disagree.** `components.py::deployment_ribbon()` reads `latest.txt` via `engine.deployments.load_latest()` (so it shows "ON-CHAIN CONNECTED" whenever a local Anvil deploy exists) while `components_wallet.py::protocol_status_banner()` reads `sepolia.json` via `engine.onchain_registry.load_any_deployment()`. Both get rendered on `/actions` right now, which is redundant at best and contradictory at worst if the two files drift.
- **`wallet_bridge.js` ABI fragments are hand-maintained.** Only the functions the UI calls live there. A rename in `FairnessGate.sol::submitAndEvaluate` or `StressOracle.sol::updateStressLevel` would not be caught by the existing `tests/test_events.py::test_contract_map_names_real_solidity_functions` guard — that one only checks the Python `CONTRACT_MAP`.
- **Multi-user / multi-session story.** `_LEDGER` and `_EVENT_LOG` globals at the top of `state.py` are shared across every Reflex browser session. Fine for a single-operator demo, wrong for any real deployment.

## 5. What is currently broken

### 5a. Connect wallet button does nothing (highest priority, user-reported)

- **Symptom**: clicking **Connect wallet** — either the navbar pill (`components_wallet.py::_wallet_badge_disconnected`) or the **Connect MetaMask** button inside `connect_prompt()` on `/actions` — does not open MetaMask. The status stays "Wallet not connected". On Brave it sometimes opens Brave Wallet instead of MetaMask.
- **Likely root causes, ranked**:
  1. **Reflex version vs `head_components` shape.** `aequitas_rx.py` uses `head_components=[rx.script(src="/wallet_bridge.js")]`. In some Reflex minor releases this argument is silently dropped, meaning the file never gets a `<script>` tag and `window.aequitasWallet` never exists. Verify first: `reflex --version`, then view-source on `http://localhost:3000/actions` and check the `<head>` for the script tag. If missing, switch to inline mounting on the page root — the fix is to add `rx.script(src="/wallet_bridge.js")` as the first child of `rx.box(...)` returned from `actions_page()`.
  2. **Asset path 404.** If Reflex is serving assets from a different subdirectory than `/wallet_bridge.js`, the script tag exists but returns 404. Check the browser devtools Network tab: filter for `wallet_bridge.js`. It must be 200.
  3. **Brave / multi-provider collision.** EIP-6963 discovery is implemented (`wallet_bridge.js::_discover`, `_pickProvider`), but the pick runs on a 30 ms `setTimeout` after the bridge installs its `eip6963:announceProvider` listener. If Brave Wallet announces faster than MetaMask, or neither announces and `window.ethereum` is Brave's, the bridge falls back to Brave. Verify in the browser console: `window.aequitasWallet._pickProvider().info.rdns` should print `io.metamask`.
  4. **`rx.call_script` promise semantics.** The retry IIFE in `AppState._bridge_call` already returns an `await` on the inner promise, but if the installed Reflex version serializes the return as `[object Promise]` rather than awaiting it, `on_wallet_connected` gets a string and the branch falls through to "Unexpected wallet response" (which lands in `wallet_last_error` and is now rendered, so a blank screen is unlikely). Verify by opening the browser console: the bridge logs `[aequitas] wallet bridge loaded · provider: <name>` via `setTimeout` 50 ms after mount.
- **Where to inspect first**:
  1. `reflex_app/aequitas_rx/aequitas_rx.py` lines 38–41 (the `head_components` argument).
  2. Browser devtools → Network → `wallet_bridge.js` (expect 200).
  3. Browser devtools → Console → look for `[aequitas] wallet bridge loaded · provider: …` breadcrumb.
  4. `reflex_app/aequitas_rx/assets/wallet_bridge.js` lines 248–281 (`connect()`).
  5. `reflex_app/aequitas_rx/state.py` lines 745–783 (`_BRIDGE_RETRY_WAIT`, `_bridge_call`, `connect_wallet`).

### 5b. Actions page still confusing for non-technical users

- **Symptom**: a jury member opens `/actions`, sees **two** deployment ribbons (legacy + new), the word "BRIDGED · CLI" on multiple cards, and the four role columns at equal visual weight. There is no "start here" call-to-action.
- **Likely causes**:
  1. `deployment_ribbon()` is still rendered unconditionally near the top of `actions_page()` on line 423 of `pages/actions.py`, duplicating the same information as `protocol_status_banner()` on line 432.
  2. Mode pill strings in `components_wallet.py::action_card_v2` and `confirm_drawer` read `LIVE` vs `BRIDGED · CLI`. "CLI" is jargon for a non-technical user.
  3. Page ordering puts the role grid before the registry block. A first-time user doesn't know whether they're ready to act.
  4. `demo_disclaimer()` fires too aggressively — every page shows the "DEMO DATA" ribbon, which deflates the perceived legitimacy of the live Sepolia flow.
- **Where to inspect first**: `reflex_app/aequitas_rx/pages/actions.py` (page composition, line 418 onwards), `reflex_app/aequitas_rx/components_wallet.py` (mode-pill label strings, drawer copy), `reflex_app/aequitas_rx/components.py::deployment_ribbon` (legacy ribbon candidate for removal on `/actions`).

### 5c. Two deployment signals can contradict each other

- **Symptom**: when a local Anvil deploy has populated `contracts/deployments/latest.txt` but `sepolia.json` has not been updated (or vice versa), `deployment_ribbon()` and `protocol_status_banner()` render different stories on the same page.
- **Likely cause**: `state.py::_refresh()` populates `deployment_*` from `load_latest()` and `registry_*` from `load_any_deployment()` independently.
- **Where to inspect first**: `state.py::_refresh` (lines 1215–1231) and `state.py::_refresh_registry` (lines 1176–1201). Then `components.py::deployment_ribbon` vs `components_wallet.py::protocol_status_banner`.

### 5d. Transaction pill stays PENDING forever on success

- **Symptom**: a live action signs, Etherscan confirms in ~15 s, but the status tile on `/actions` still shows PENDING until the user reloads.
- **Likely cause**: `wallet_bridge.js::runAction` does not await `tx.wait()` or subscribe to block events; `on_tx_submitted` writes `last_tx_status="pending"` and there's no follow-up.
- **Where to inspect first**: `wallet_bridge.js::runAction` (lines 327–380), `state.py::on_tx_submitted` (lines 1131–1161).

### 5e. Brave / multi-provider detection edge case

- **Symptom**: user in Brave reports "Connect wallet does nothing" or "opens Brave Wallet instead of MetaMask".
- **Likely cause**: race between Brave Wallet and MetaMask's EIP-6963 announcements. `_pickProvider` runs once on a 30 ms timeout after page load and again lazily when `_ethProvider()` is called. If MetaMask announces after 30 ms, the wrong provider is cached.
- **Where to inspect first**: `wallet_bridge.js` lines 132–178 (`_providers` Map, `_discover`, `_pickProvider`), and line 391 (`setTimeout(_pickProvider, 30)`).

## 6. Files Codex should inspect first

Ordered by relevance to the wallet + Actions UX work. Exact paths, all relative to repo root.

1. `reflex_app/aequitas_rx/aequitas_rx.py` — app constructor, route registrations, `head_components=[rx.script(src="/wallet_bridge.js")]`. Confirm the script tag actually lands in the served `<head>`.
2. `reflex_app/aequitas_rx/assets/wallet_bridge.js` — the entire browser-side wallet layer. EIP-6963 discovery, `connect`, `switchToSepolia`, `runAction`, `getState`, chain/account event emitters via `CustomEvent("aequitas:wallet")`.
3. `reflex_app/aequitas_rx/state.py` — `AppState` with all wallet/registry fields, the `_bridge_call` JS retry wrapper, the `_ACTIONS: ClassVar` catalogue, the `can_run_live_action` / `live_action_blocker` computed vars.
4. `reflex_app/aequitas_rx/components_wallet.py` — `wallet_badge`, `protocol_status_banner`, `confirm_drawer`, `action_card_v2`, `role_column`, `connect_prompt`, `wallet_event_bridge`, `_wallet_error_strip`.
5. `reflex_app/aequitas_rx/pages/actions.py` — `/actions` composition: hero, legacy ribbon, status banner, connect prompt, recent-action strip, role grid, registry block, deploy runbook (gated on `~registry_present`), confirm drawer, wallet event bridge.
6. `reflex_app/aequitas_rx/components.py` — `navbar()`, `pill()`, `deployment_ribbon()`, `page_header()`, KPI strip, `demo_disclaimer()`. The `navbar()` late-imports `wallet_badge` to avoid a cycle.
7. `engine/onchain_registry.py` — `load_registry`, `load_any_deployment`, `OnchainRegistry`, `ContractRecord`, `SEPOLIA_CHAIN_ID = 11155111`, `etherscan_address`, `etherscan_tx`, `short_address`.
8. `contracts/deployments/sepolia.json` — populated; 8 contracts, `verified:true`, deployer `0xa275c7e…`, `deployed_at` `2026-04-21T21:33:00Z`.
9. `contracts/deployments/sepolia.schema.md` — schema reference + populate runbook.
10. `contracts/broadcast/Deploy.s.sol/11155111/run-latest.json` — Foundry broadcast log that `import_broadcast.py` consumes.
11. `scripts/import_broadcast.py` — broadcast → registry helper. Idempotent; preserves `$schema`, `rpc_hint`, `notes`.
12. `tests/test_import_broadcast.py`, `tests/test_onchain_registry.py` — pinning tests. Run first to confirm baseline before changes.
13. `engine/deployments.py` — legacy `latest.txt` loader. Still used by `deployment_ribbon()`.
14. `contracts/src/FairnessGate.sol`, `StressOracle.sol`, `BackstopVault.sol`, `VestaRouter.sol`, `CohortLedger.sol`, `MortalityOracle.sol`, `LongevaPool.sol`, `BenefitStreamer.sol` — signatures used by the JS ABI fragments in `wallet_bridge.js::ABI`. Must stay in sync.
15. `contracts/script/Deploy.s.sol`, `contracts/foundry.toml` — what the populated `sepolia.json` reconciles against.
16. `run_app.py`, `reflex_app/rxconfig.py`, `reflex_app/requirements.txt` — app entry + Reflex config.
17. `CODEX_HANDOFF.md` (the older one, 309 lines) — mostly superseded by this document, but section 12 ("Risks / gotchas") still applies verbatim.

## 7. Files changed recently

Current session + prior session's wallet/Actions + registry work:

- `scripts/import_broadcast.py` — new; broadcast-log → registry helper, stdlib-only, CLI with `--dry-run`/`--verified`/`--chain-id`.
- `tests/test_import_broadcast.py` — new; 18 tests pinning the parser shape, empty-broadcast rejection, CLI exit codes, metadata preservation, and a round-trip through `engine.onchain_registry.load_registry`.
- `contracts/deployments/sepolia.json` — regenerated from the broadcast log; all 8 contracts populated, `verified:true`.
- `reflex_app/aequitas_rx/assets/wallet_bridge.js` — rewritten; EIP-6963 discovery, `STATE` cache, `CustomEvent("aequitas:wallet")` emitter, ethers CDN loader, `runAction` dispatch with per-action `DEMO_ARGS` and minimal `ABI` per contract, `getState` snapshot.
- `reflex_app/aequitas_rx/state.py` — added `_BRIDGE_RETRY_WAIT` / `_bridge_call` JS retry wrapper; `connect_wallet`, `switch_to_sepolia`, `confirm_action` now all use it; added `refresh_wallet_state` + `on_wallet_state_snapshot` handlers and `live_action_blocker` / `can_run_live_action` computed vars.
- `reflex_app/aequitas_rx/components_wallet.py` — added `_WALLET_EVENT_LISTENER_JS`, `wallet_event_bridge()`, `_wallet_error_strip()`. `connect_prompt()` now leads with the error strip.
- `reflex_app/aequitas_rx/pages/actions.py` — imported `wallet_event_bridge`, wrapped `_deploy_runbook()` in `rx.cond(~AppState.registry_present, …)`, mounted `wallet_event_bridge()` at the end of `actions_page()`.
- `engine/onchain_registry.py` — unchanged this session; added in a prior session. Still the single entry point for Reflex.
- `CODEX_HANDOFF_v2.md` — this file.

## 8. Current Sepolia / deployment context

- **Contracts are already deployed on Sepolia.** Deployer EOA `0xa275c7e279fb51f419db50244eba5f0f0197e9e0`. Broadcast log: `contracts/broadcast/Deploy.s.sol/11155111/run-latest.json`. Populated registry: `contracts/deployments/sepolia.json`. Codex must **not** redeploy.
- **Eight addresses** (lowercase, verbatim from the broadcast log; Etherscan resolves either case):
  - CohortLedger `0x4948cbce1c80f166aab30017bd31825da81e09dc`
  - FairnessGate `0x334cacf2e0d8cf2c68e96d66d87f21ecb6e13f75`
  - MortalityOracle `0xd75cd2f76fd51c6a091b98ebb9bb07f4323dd2fd`
  - LongevaPool `0x3fa350a007b641c8f2d1cc4c29a41d9999f19a71`
  - BenefitStreamer `0x0c58b0f69cb3a9e9ec61810951c905400e768e8b`
  - VestaRouter `0x0de6addf833d1af1650ba6a9e7c10e76ec7c3a19`
  - StressOracle `0x4d3e155d4243e372917344968fd3907a0462c5c7`
  - BackstopVault `0x6a34eaa0e10a449671e125873d2036aa989ae826`
- **RPC URL** lives in the user's local `contracts/.env` as `SEPOLIA_RPC_URL`. Not committed. `foundry.toml` references it as `${SEPOLIA_RPC_URL}`.
- **Etherscan API key** lives in the same local `contracts/.env` as `ETHERSCAN_API_KEY`. Not committed.
- **MetaMask wallet exists, funded with Sepolia ETH.** User signs with MetaMask — never pastes a private key into the Reflex UI.
- **Expected non-technical user flow**:
  1. Land on `/` — see the scheme KPIs.
  2. Navigate to `/actions` — see the status banner tiles (Wallet, Network, Deployment, Last action). Deployment tile reads `VERIFIED · SEPOLIA`.
  3. Click **Connect wallet** (navbar pill or Connect prompt). MetaMask opens. Approve.
  4. Wallet tile flips to "Connected to Sepolia", navbar badge shows `0x….` + green `SEPOLIA` pill.
  5. If the wallet is on Mainnet or another chain: the Wallet tile turns amber, a visible **Switch to Sepolia** button fires `wallet_switchEthereumChain` (or `wallet_addEthereumChain` if Sepolia isn't in the user's MetaMask yet).
  6. Click a card in the role grid (e.g. **Publish fairness stress result**). Confirmation drawer opens with a plain-English summary, Actuarial meaning / Protocol meaning, REVERSIBILITY ribbon, and a collapsed Advanced accordion.
  7. Click **Sign in MetaMask**. MetaMask opens, user approves.
  8. Recent-action strip and status banner flip to PENDING with an Etherscan link. User clicks through to see confirmation.
  9. At no point does a terminal command, private key, raw calldata, or `.env` appear on screen (the deploy runbook is hidden when `registry_present` is true).

## 9. Immediate next task for Codex

Fix wallet connection on `/actions` and tighten the page so a non-technical juror has exactly one path to sign a live transaction.

Concrete steps, in order:

1. **Verify bridge delivery.** Run `cd reflex_app && reflex run`. Open `http://localhost:3000/actions`. Check devtools Network: `wallet_bridge.js` must return HTTP 200. Check Console: must log `[aequitas] wallet bridge loaded · provider: <name>` within ~50 ms. If the script tag is absent from `<head>`, the Reflex version is dropping `head_components`. Fix: inject the script inline as the first child of the `rx.box(...)` returned by `actions_page()` in `reflex_app/aequitas_rx/pages/actions.py`, and mirror the same change on `overview_page()` so the navbar wallet badge works from the landing page.
2. **Verify provider choice.** In devtools Console: `window.aequitasWallet._pickProvider().info.rdns` should be `io.metamask`. If it returns `brave` or `legacy.window.ethereum`, raise the discovery timeout in `wallet_bridge.js` line 391 from `30` to `150` ms, or expose a debug-only manual picker (`window.aequitasWallet.forceMetaMask()`) that searches `_providers` for `io.metamask` and sets `_chosenProvider` unconditionally.
3. **Smoke-test `connect()`.** In devtools Console: `await window.aequitasWallet.connect()`. MetaMask must pop. The returned object must be `{ok:true, address:'0x…', chainId:<int>, providerName:'MetaMask'}`. If it's `{ok:false, error:'MetaMask not found.'}`, provider discovery failed (see step 2). If MetaMask pops but Reflex state doesn't update, the problem is `rx.call_script` callback delivery, not the bridge.
4. **De-duplicate deployment signalling on `/actions`.** Remove the `deployment_ribbon()` call on line 423 of `pages/actions.py` — `protocol_status_banner()` already carries the Deployment tile. Keep `deployment_ribbon()` on the other pages (Overview etc.) or delete it entirely if Codex decides a single global signal is cleaner. Either way, `/actions` must not render two contradictory ribbons.
5. **Rename mode pills to non-technical strings.** In `components_wallet.py::action_card_v2` and `confirm_drawer`, replace `"BRIDGED · CLI"` with `"OFF-CHAIN"` and `"LIVE · ON-CHAIN"` with `"LIVE ON SEPOLIA"`. Update the `_ACTIONS` `mode` strings in `state.py` to match (`"Bridged"` → `"Off-chain"`). Also update the `rx.cond(AppState.confirm_is_live, "Sign in MetaMask", "Acknowledge and continue")` button already uses reasonable copy — leave it.
6. **Strengthen blocker copy.** In `components_wallet.py::_confirm_body`, the text `"You are about to trigger a change that may be written to the audit chain"` should become `"This action will be written to the on-chain audit trail once signed."` for live actions (keep the softer phrasing for off-chain actions).
7. **Add a "start here" affordance.** Above `_role_grid()` in `pages/actions.py`, add a one-line highlight when `registry_present && !wallet_connected`: "Start by connecting your wallet — then pick any action from the four columns below." Wire it to `AppState.connect_wallet` so clicking acts as a shortcut.
8. **Add `provider.waitForTransaction(hash)`.** In `wallet_bridge.js::runAction`, after `const tx = await contract[func](...)`, kick off a fire-and-forget `(async () => { await tx.wait(); window.dispatchEvent(new CustomEvent('aequitas:tx', {detail:{hash:tx.hash, confirmed:true}})); })()`. In `components_wallet.py::wallet_event_bridge`, extend the window listener to also listen for `aequitas:tx` and click a second hidden button `#__aequitas_tx_confirmed` that calls a new `AppState.on_tx_confirmed(hash)` handler. That handler must flip `last_tx_status` from `"pending"` to `"confirmed"`.
9. **Keep running `python3 /tmp/pytest_shim.py tests/`.** The target is 134 passed, 0 failed. Any new Python code (e.g. the new state handler) must come with pinning tests.

Do **not**:

- Redeploy any Solidity contract.
- Rewrite `engine/`, any existing Reflex page besides `actions.py` / `state.py` / `components.py` / `components_wallet.py`, or the test suite shim.
- Add new Python or JS package dependencies beyond the `ethers@6.13.2` CDN script already loaded by `wallet_bridge.js`.
- Introduce a competing wallet library (wagmi / web3modal / rainbowkit).
- Touch `contracts/deployments/sepolia.json` unless you re-run `scripts/import_broadcast.py` — hand-editing it is how the two-banner divergence started.

## 10. Acceptance criteria

All must be green before declaring the Actions page jury-ready.

- **Connect wallet opens MetaMask.** Clicking **Connect wallet** (navbar pill or `connect_prompt`) opens the MetaMask extension within one second. Works in Chrome, Brave (with MetaMask installed), Edge. In Brave the MetaMask popup opens, not the Brave Wallet popup.
- **Wallet status updates visibly.** Within one second of the user approving in MetaMask, the navbar badge flips to `0x….` + green `SEPOLIA` pill, and the Wallet tile in `protocol_status_banner()` reads "Connected to Sepolia".
- **Sepolia network is detected or switch is prompted.** If the wallet is on another chain, the Wallet tile turns amber, the Network tile shows the current chain name, and a visible **Switch to Sepolia** button triggers `wallet_switchEthereumChain` (with the `wallet_addEthereumChain` fallback path) in MetaMask.
- **Existing deployment is recognised automatically.** On page load, with `sepolia.json` populated, the Deployment tile shows `VERIFIED · SEPOLIA`, the registry block lists all 8 contracts with Etherscan links, and the deploy runbook is hidden.
- **Live actions are visibly separated from off-chain actions.** Live cards show a green `LIVE ON SEPOLIA` pill; off-chain cards show a neutral `OFF-CHAIN` pill. The word "CLI" does not appear anywhere on the page by default. Live actions are disabled with an explanatory tooltip when `~can_run_live_action`.
- **Confirmation drawer is jury-safe.** Opens on card click. Shows label, plain-English summary, Actuarial meaning, Protocol meaning, REVERSIBILITY ribbon. "Advanced · technical details" is collapsed by default and contains the contract, function, params, and deployed address. BLOCKED ribbon surfaces `AppState.live_action_blocker` whenever the action can't run.
- **Live signing round-trips.** After Connect + Sepolia + populated registry, clicking **Publish fairness stress result**, confirming in the drawer, and signing in MetaMask results in `last_tx_status="pending"` with a valid tx hash and a working Etherscan deep-link. Within ~30 seconds (Sepolia block time), the pill flips to `CONFIRMED` without a page refresh. Operations feed gets `tx_submitted` (and later `tx_confirmed`) entries.
- **No shell-oriented copy by default.** On a fully-connected machine (wallet + Sepolia + registry populated), the `/actions` page contains zero references to `forge`, `cast`, `$SEPOLIA_RPC_URL`, `.env`, `PRIVATE_KEY`, `ETHERSCAN_API_KEY`. Those references appear only inside the Advanced accordion or when in the pre-deployment state.
- **One deployment signal, not two.** `/actions` renders the `protocol_status_banner` Deployment tile. It does **not** render the legacy `deployment_ribbon()` on the same page.
- **All existing tests still pass.** `python3 /tmp/pytest_shim.py tests/` → `134 passed, 0 failed` (or more, if Codex adds new tests).
- **All modified Python files compile cleanly.** `python3 -m py_compile engine/*.py reflex_app/aequitas_rx/*.py reflex_app/aequitas_rx/pages/*.py scripts/*.py tests/test_*.py` exits zero.

## 11. Exact run/test instructions

All commands run from `/Users/tarafimohammedyazid/Documents/Claude/Projects/aequitas`.

Python test suite (no pytest install needed — repo targets the minimal shim):

```
python3 /tmp/pytest_shim.py tests/
```

Expected tail: `134 passed, 0 failed`.

Syntax-check every modified Python file:

```
python3 -m py_compile \
    engine/onchain_registry.py \
    reflex_app/aequitas_rx/state.py \
    reflex_app/aequitas_rx/components.py \
    reflex_app/aequitas_rx/components_wallet.py \
    reflex_app/aequitas_rx/aequitas_rx.py \
    reflex_app/aequitas_rx/pages/actions.py \
    scripts/import_broadcast.py \
    tests/test_import_broadcast.py
```

Run the Reflex app locally:

```
cd reflex_app
reflex run
```

Frontend on `http://localhost:3000`; backend on `http://localhost:8000`. Run `reflex init` first if this is a fresh machine.

Solidity build + Foundry tests:

```
cd contracts
forge build
forge test -vv
```

Regenerate the Sepolia registry from the broadcast log (idempotent; preserves `$schema`, `rpc_hint`, `notes` comments in the existing file):

```
python3 scripts/import_broadcast.py \
    contracts/broadcast/Deploy.s.sol/11155111/run-latest.json \
    contracts/deployments/sepolia.json \
    --verified all
```

Dry-run (prints the computed JSON to stdout, does not touch the file):

```
python3 scripts/import_broadcast.py \
    contracts/broadcast/Deploy.s.sol/11155111/run-latest.json \
    contracts/deployments/sepolia.json \
    --dry-run --verified all
```

Verify the registry loads via the canonical entry point:

```
python3 -c "from engine.onchain_registry import load_any_deployment; r = load_any_deployment(); print(r.chain_id, len(r.contracts), r.verified)"
```

Expected: `11155111 8 True`.

## 12. Risks / gotchas

- **Reflex version sensitivity (highest-impact gotcha).** `rx.call_script(..., callback=EventHandler)` and `head_components=[rx.script(...)]` have both shifted across Reflex minor releases. If `reflex --version` is < 0.6, the callback semantics are different and both the connect flow and the event bridge behave inertly. `reflex_app/requirements.txt` pins `reflex>=0.6.0` but a local virtualenv may hold a newer 0.7.x or 0.8.x where the `head_components` argument name or the assets-serving path changed. Pin the version before debugging.
- **`AppState` is a module-level singleton.** `_LEDGER` and `_EVENT_LOG` at the top of `state.py` are shared across all browser sessions. Fine for a demo. For a multi-user deploy, those must move per-session.
- **`_ACTIONS` must remain `ClassVar`.** Reflex treats class-level mutable attributes as state vars unless annotated `ClassVar`. Any new constant table in `AppState` needs the same annotation.
- **`f"{AppState.var}"` does not work.** `AppState` fields are Reflex `Var`s, not strings. String interpolation must go through separate `rx.text(...)` children or `Var` concatenation.
- **`on_click=lambda: AppState.open_action(key)` does not work.** Use the `EventSpec` form: `on_click=AppState.open_action(key)`. Already correct in `components_wallet.py::action_card_v2`; match that pattern for any new handlers.
- **Wallet bridge path is absolute (`/wallet_bridge.js`).** If the app is ever mounted under a sub-path or behind a reverse proxy, that path will 404. Switch to a Reflex-aware helper (`rx.asset("wallet_bridge.js")` if available) or inline the script.
- **Minimal ABIs in `wallet_bridge.js::ABI` are hand-maintained.** A Solidity function rename will not break the build. The existing `tests/test_events.py::test_contract_map_names_real_solidity_functions` guards the Python-side `CONTRACT_MAP` but not the JS ABIs. Codex should add a parallel test that greps the JS file against the Solidity sources.
- **`DEMO_ARGS` uses placeholder inputs.** `open_retirement` signs `0x0000…0001` as the retiree. Transactions succeed but don't reflect scheme state. A jury-grade run needs real args sourced from `AppState`.
- **Transaction hash casing.** `ContractRecord.address` and `last_tx_hash` are preserved verbatim from whatever the source wrote (lowercase from Foundry broadcast logs). Etherscan resolves both forms; the UI does not apply EIP-55 checksum.
- **Nothing caches the Sepolia registry across requests.** `AppState.refresh_view` → `_refresh` re-reads `sepolia.json` from disk on every navigation. Fine for local dev; watch out in production.
- **Brave Wallet + MetaMask race.** EIP-6963 discovery relies on both wallets announcing before the 30 ms `setTimeout` fires. If MetaMask is slow to inject on a cold page, Brave wins. Codex can raise the timeout or add a "Use MetaMask" hint on the connect prompt.
- **`rx.fragment()` is not a free no-op.** Mixing literal strings and `Var` children inside `rx.fragment()` or `rx.text()` is a Reflex footgun. All dynamic text in this codebase is kept as its own `rx.text(...)` node; preserve that.
- **`ethers` CDN.** `wallet_bridge.js` pulls `ethers@6.13.2` from cdnjs at dispatch time. If cdnjs returns 404, `runAction` errors out with "failed to load ethers.js from CDN" — `connect` and `switchToSepolia` do not depend on ethers and will still work.
- **Uncertain**: whether MetaMask popups fire reliably on `rx.call_script(...)` in Firefox. All flows were designed against Chromium browsers.
- **Uncertain**: whether Reflex's current assets-serving path is `/wallet_bridge.js` (absolute root) or `/_next/static/.../wallet_bridge.js` on the installed version. Verify via Network tab.

## 13. Codex starter prompt

```
You are continuing work on the Aequitas repository at
/Users/tarafimohammedyazid/Documents/Claude/Projects/aequitas.

Do not restart from zero. The repo already has:
- a complete Python actuarial engine under engine/ (134 tests passing)
- 8 Solidity contracts deployed on Sepolia (contracts/src/)
- a populated deployment registry at contracts/deployments/sepolia.json
  with all 8 addresses, tx hashes, verified:true, and deployer
  0xa275c7e279fb51f419db50244eba5f0f0197e9e0
- a Reflex frontend under reflex_app/aequitas_rx/ with 8 pages, including
  an Operator Action Center at /actions
- a browser wallet bridge at reflex_app/aequitas_rx/assets/wallet_bridge.js
  exposing window.aequitasWallet.{connect, switchToSepolia, runAction,
  hasEthereum, getState} with EIP-6963 discovery
- a JS→Reflex event bridge via CustomEvent("aequitas:wallet") that
  forwards MetaMask chainChanged/accountsChanged into
  AppState.refresh_wallet_state

Read CODEX_HANDOFF_v2.md at the repo root before making any changes.
Section 5 lists the current breakage; section 9 is the exact punch list;
section 10 is the acceptance criteria.

Your immediate task: make wallet connection work reliably on /actions
and make the Actions page usable by a non-technical jury member.

Scope, in order:
1. Verify wallet_bridge.js is actually served (Network 200, Console logs
   "[aequitas] wallet bridge loaded"). If the <script> tag is missing
   from <head>, the installed Reflex version is dropping head_components;
   fix by injecting rx.script(src="/wallet_bridge.js") inline as the
   first child of actions_page() (and overview_page() for the navbar).
2. Smoke-test connect() from the browser Console. If the popup appears
   but Reflex state doesn't update, the callback delivery is the bug;
   if the popup doesn't appear, provider discovery is the bug. The
   retry IIFE in AppState._bridge_call and the EIP-6963 picker in
   wallet_bridge.js::_pickProvider are the two places to look.
3. Remove the duplicate deployment signal on /actions: drop the
   deployment_ribbon() call in pages/actions.py (protocol_status_banner
   already carries Deployment state).
4. Rename mode pills to non-technical strings ("LIVE ON SEPOLIA",
   "OFF-CHAIN") in components_wallet.py and in AppState._ACTIONS.
5. Add a "start here — connect your wallet" one-liner above the role
   grid when registry_present && !wallet_connected.
6. Implement tx-confirmation propagation: in wallet_bridge.js::runAction
   fire-and-forget a tx.wait() that dispatches CustomEvent("aequitas:tx",
   {detail:{hash, confirmed:true}}). Extend wallet_event_bridge to catch
   it and flip AppState.last_tx_status from "pending" to "confirmed".
7. Run the full Python test suite and keep it at 134/134.

Hard constraints:
- Do not redeploy the Solidity contracts.
- Do not rewrite engine/ or any Reflex page other than actions.py,
  state.py, components.py, components_wallet.py.
- Do not add new Python or JS dependencies beyond the ethers CDN
  already used by wallet_bridge.js.
- Do not hand-edit contracts/deployments/sepolia.json; regenerate it
  via `python3 scripts/import_broadcast.py ... --verified all` if it
  ever drifts.

Finish when every checkbox in CODEX_HANDOFF_v2.md §10 is green, then
run:
  python3 /tmp/pytest_shim.py tests/
  python3 -m py_compile $(git ls-files '*.py')
  cd reflex_app && reflex run
and manually verify the Connect → Sepolia → Publish-stress → Confirmed
round-trip against the live deployment.
```
