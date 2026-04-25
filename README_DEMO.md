# Aequitas Local Demo Flow

This is the operator flow for a jury demo. It is intentionally dev-only: deployment is a backend subprocess, not a MetaMask action and not normal user UX.

## One terminal command

```bash
./run_demo.sh
```

The launcher loads project-root `.env`, verifies `AEQUITAS_DEVTOOLS=1`, starts the Reflex app from `reflex_app`, prints the local URL, and opens `http://localhost:3000/contracts` on macOS.

## Required local `.env`

Copy `.env.example` to `.env` and fill in:

```bash
AEQUITAS_DEVTOOLS=1
ANVIL_RPC_URL=http://127.0.0.1:8545
ANVIL_PK=<one of Anvil's local deterministic private keys>
```

Do not use a real funded private key for `ANVIL_PK`. Sepolia variables are optional and are not required for the local demo setup.

## In-app demo setup

Open `Contracts / Proof`, then use the dev-only Developer Tools panel:

1. Click `Run full local demo setup`.
2. The app starts Anvil if needed.
3. The app deploys the local protocol stack.
4. The app imports the latest local broadcast into `contracts/deployments/local.json`.
5. The app reloads the registry so live statuses update.

Logs are shown in the panel with secrets redacted.
