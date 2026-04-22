# `sepolia.json` — deployment registry schema

This file is the single source of truth the Reflex app reads for:

- Which contracts are deployed on Sepolia
- Their addresses
- The tx hash that created each one
- Whether source has been verified on Etherscan

## Shape

```jsonc
{
  "chain_id":       11155111,                         // int, required
  "chain_name":     "Sepolia Testnet",                // string, informational
  "deployer":       "0xabc...",                       // EOA that ran Deploy.s.sol
  "deployed_at":    "2026-04-20T17:30:00Z",           // ISO-8601 UTC
  "explorer_base":  "https://sepolia.etherscan.io",   // used to build links
  "rpc_hint":       "https://sepolia.infura.io/...",  // UI hint only — no secrets
  "verified":       true,                              // overall verification state
  "contracts": {
    "CohortLedger": {
      "address":  "0x...",
      "tx_hash":  "0x...",
      "verified": true
    },
    "FairnessGate":    { "address": "0x...", "tx_hash": "0x...", "verified": true },
    "MortalityOracle": { "address": "0x...", "tx_hash": "0x...", "verified": true },
    "LongevaPool":     { "address": "0x...", "tx_hash": "0x...", "verified": true },
    "BenefitStreamer": { "address": "0x...", "tx_hash": "0x...", "verified": true },
    "VestaRouter":     { "address": "0x...", "tx_hash": "0x...", "verified": true },
    "StressOracle":    { "address": "0x...", "tx_hash": "0x...", "verified": true },
    "BackstopVault":   { "address": "0x...", "tx_hash": "0x...", "verified": true }
  }
}
```

## Populating after deploy

1. Deploy:

   ```bash
   cd contracts
   forge script script/Deploy.s.sol \
       --rpc-url "$SEPOLIA_RPC_URL" \
       --private-key "$PRIVATE_KEY" \
       --broadcast --verify \
       --etherscan-api-key "$ETHERSCAN_API_KEY"
   ```

2. Foundry will print a deployment table and write a broadcast log under
   `contracts/broadcast/Deploy.s.sol/11155111/run-latest.json`. Copy each
   contract's `contractAddress` and `hash` into the matching block here.

3. Save. The Reflex app picks it up on the next page load — the status
   banner will switch from **OFF-CHAIN ONLY** to **ON-CHAIN · SEPOLIA**.

## Safety

Secrets (private key, full RPC URL with API token) belong in a local
`.env` file, **never** in this registry. `rpc_hint` is meant to be a
visible, un-authenticated URL or a template placeholder only.
