/*
 * Aequitas browser-side wallet bridge.
 *
 * All wallet logic runs in the user's browser — the Reflex server never
 * sees a private key. Python only `rx.call_script(...)`s into these
 * functions and receives JSON-like results through a callback handler.
 *
 * Surface:
 *   window.aequitasWallet.connect()          -> {ok, address?, chainId?, error?}
 *   window.aequitasWallet.switchToSepolia()  -> {ok, chainId?, error?}
 *   window.aequitasWallet.runAction(key,opts) -> {ok, hash?, confirmed?, error?}
 *   window.aequitasWallet.getState()         -> synchronous snapshot object
 *
 * All three action functions return a Promise that resolves to a plain
 * object. Reflex awaits the promise via rx.call_script and passes the
 * result to the Python callback.
 *
 * Provider selection follows EIP-6963 so MetaMask is picked even when
 * Brave Wallet / Coinbase Wallet also inject window.ethereum. If no
 * EIP-6963 announcements arrive within a short window we fall back to
 * window.ethereum.
 */
(function () {
  "use strict";

  const SEPOLIA_HEX = "0xaa36a7";      // 11155111
  const SEPOLIA_INT = 11155111;

  // Minimal ABIs — only the functions we call live from the UI. Keeping
  // these tiny means we don't bundle the whole Foundry artifact set.
  const ABI = {
    FairnessGate: [
      "function setBaseline(uint16[] cohorts, int256[] epvs)",
      "function submitAndEvaluate(string name, uint16[] cohorts, int256[] newEpvs, uint256 delta) returns (uint256, bool)"
    ],
    StressOracle: [
      "function updateStressLevel(uint256 level, bytes32 reasonCode, bytes32 dataHash)"
    ],
    BackstopVault: [
      "function deposit() payable",
      "function release(uint256 amount)"
    ],
    VestaRouter: [
      "function openRetirement(address retiree, uint256 initialFunding, uint128 annualBenefit, uint64 startTs)"
    ],
    CohortLedger: [
      "function registerMember(address wallet, uint16 birthYear)",
      "function contribute(address wallet, uint256 amount) returns (uint256)",
      "function setPiuPrice(uint256 newPrice)"
    ],
    MortalityBasisOracle: [
      "function publishBasis(uint64 version, bytes32 baselineId, bytes32 cohortDigest, uint32 credibilityBps, uint64 effectiveDate, bytes32 studyHash, uint64 exposureScaled, uint32 observedDeaths, uint64 expectedDeathsScaled, bool advisory)"
    ],
    MortalityOracle: [
      "function confirmDeath(address wallet, uint64 deathTimestamp, bytes32 proofHash)"
    ],
    LongevaPool: [
      "function harvestYield() returns (uint256)"
    ]
  };

  // Demo argument packs for each action key. Intentionally small &
  // sensible so a juror can sign and watch the tx go through without
  // needing to type numbers. Tweak via the Advanced drawer later.
  const DEMO_ARGS = {
    publish_baseline: () => ({
      // Two-cohort stub: 1980 cohort EPV = 1e18, 1990 cohort EPV = 8.5e17.
      args: [[1980, 1990], ["1000000000000000000", "850000000000000000"]]
    }),
    publish_piu_price: () => ({
      args: ["1030000000000000000"]
    }),
    publish_mortality_basis: () => ({
      args: [
        "1",
        "0x" + "6d6f72745f62617369735f7631".padEnd(64, "0"),
        "0x" + "ab12".padEnd(64, "0"),
        "2500",
        String(Math.floor(Date.now() / 1000)),
        "0x" + "cd34".padEnd(64, "0"),
        "2500000",
        "34",
        "301000",
        true
      ]
    }),
    submit_proposal: () => ({
      args: [
        "Trim youngest cohort benefit",
        [1980, 1990],
        ["1000000000000000000", "820000000000000000"],   // -3% on 1990
        "50000000000000000"                              // delta = 5e16 = 5%
      ]
    }),
    publish_stress: () => ({
      // level = 75 (0..100 scaled), reasonCode & dataHash as keccak-ish bytes32
      args: [
        "75",
        "0x" + "70393500".padEnd(64, "0"),   // "p95" hint
        "0x" + "d47a".padEnd(64, "0")         // data hash stub
      ]
    }),
    fund_reserve: () => ({
      value: "10000000000000000",     // 0.01 ETH
      args: []
    }),
    release_reserve: () => ({
      args: ["5000000000000000"]       // 0.005 ETH
    }),
    open_retirement: () => ({
      // placeholder — the retiree address should be chosen in the UI
      args: [
        "0x0000000000000000000000000000000000000001",
        "1000000000000000000",
        "50000000000000000",
        String(Math.floor(Date.now() / 1000))
      ]
    })
  };

  // ------------------------------------------------------------------
  // Cached wallet state. Kept fresh by chainChanged/accountsChanged
  // subscriptions so Reflex can poll a synchronous snapshot and react.
  // ------------------------------------------------------------------
  const STATE = {
    ok: false,
    connected: false,
    address: "",
    chainId: 0,
    providerName: "",
    error: ""
  };

  function _snapshot(extra) {
    return Object.assign({}, STATE, extra || {});
  }

  function _emitUpdate(reason) {
    try {
      const ev = new CustomEvent("aequitas:wallet", {
        detail: Object.assign({ reason: String(reason || "update") }, STATE)
      });
      window.dispatchEvent(ev);
    } catch (_) {}
  }

  // ------------------------------------------------------------------
  // EIP-6963 provider discovery. Many browsers inject more than one
  // provider (Brave Wallet + MetaMask). EIP-6963 lets each provider
  // announce itself; we pick MetaMask when available, else the first
  // announcer, else fall back to window.ethereum.
  // ------------------------------------------------------------------
  const _providers = new Map();   // uuid -> { info, provider }
  let _chosenProvider = null;

  function _onAnnounce(ev) {
    try {
      const detail = ev && ev.detail;
      if (!detail || !detail.info || !detail.provider) return;
      _providers.set(detail.info.uuid || detail.info.rdns, detail);
    } catch (_) {}
  }

  function _discover() {
    // Ask any already-live provider to re-announce itself.
    try { window.addEventListener("eip6963:announceProvider", _onAnnounce); } catch (_) {}
    try { window.dispatchEvent(new Event("eip6963:requestProvider")); } catch (_) {}
  }

  function _pickProvider() {
    // Prefer MetaMask by rdns. Fall back to the first announced, then
    // to window.ethereum (which may itself be a multi-provider proxy).
    // Re-evaluate on each call so a late MetaMask announcement can
    // replace an earlier Brave/legacy fallback.
    let chosen = null;
    for (const entry of _providers.values()) {
      if ((entry.info.rdns || "").toLowerCase() === "io.metamask") {
        chosen = entry;
        break;
      }
    }
    if (!chosen) {
      const first = _providers.values().next().value;
      if (first) chosen = first;
    }
    if (!chosen && _chosenProvider && _chosenProvider.provider) {
      chosen = _chosenProvider;
    }
    if (chosen) {
      _chosenProvider = chosen;
      STATE.providerName = chosen.info.name || "unknown";
      return chosen;
    }
    if (typeof window !== "undefined" && window.ethereum) {
      _chosenProvider = {
        info: { name: "window.ethereum", rdns: "legacy.window.ethereum", uuid: "legacy" },
        provider: window.ethereum
      };
      STATE.providerName = "window.ethereum";
      return _chosenProvider;
    }
    return null;
  }

  function _ethProvider() {
    const p = _pickProvider();
    return p ? p.provider : null;
  }

  function forceMetaMask() {
    for (const entry of _providers.values()) {
      if ((entry.info.rdns || "").toLowerCase() === "io.metamask") {
        _chosenProvider = entry;
        STATE.providerName = entry.info.name || "MetaMask";
        return true;
      }
    }
    return false;
  }

  function hasEthereum() {
    return _ethProvider() != null;
  }

  function hexToInt(hex) {
    if (hex == null) return 0;
    if (typeof hex === "number") return hex;
    try { return parseInt(hex, 16); } catch (e) { return 0; }
  }

  // ------------------------------------------------------------------
  // Ethers loader — lazy, from a CDN pin, so page load stays lean.
  // ------------------------------------------------------------------
  let _ethersPromise = null;
  function loadEthers() {
    if (window.ethers) return Promise.resolve(window.ethers);
    if (_ethersPromise) return _ethersPromise;
    _ethersPromise = new Promise((resolve, reject) => {
      const s = document.createElement("script");
      s.src = "https://cdnjs.cloudflare.com/ajax/libs/ethers/6.13.2/ethers.umd.min.js";
      s.async = true;
      s.onload = () => {
        if (window.ethers) resolve(window.ethers);
        else reject(new Error("ethers.js failed to expose window.ethers"));
      };
      s.onerror = () => reject(new Error("failed to load ethers.js from CDN"));
      document.head.appendChild(s);
    });
    return _ethersPromise;
  }

  // ------------------------------------------------------------------
  // Event subscriptions — installed once per provider so chain/account
  // switches in MetaMask flow back into Reflex state.
  // ------------------------------------------------------------------
  let _subscribedProvider = null;

  function _subscribe(provider) {
    if (!provider || _subscribedProvider === provider) return;
    _subscribedProvider = provider;
    try {
      provider.on("chainChanged", async (cidHex) => {
        STATE.chainId = hexToInt(cidHex);
        _emitUpdate("chainChanged");
      });
    } catch (_) {}
    try {
      provider.on("accountsChanged", (accs) => {
        if (Array.isArray(accs) && accs.length > 0) {
          STATE.address = String(accs[0]).toLowerCase();
          STATE.connected = true;
        } else {
          STATE.address = "";
          STATE.connected = false;
        }
        _emitUpdate("accountsChanged");
      });
    } catch (_) {}
  }

  // ------------------------------------------------------------------
  // Wallet plumbing
  // ------------------------------------------------------------------
  async function connect() {
    const provider = _ethProvider();
    if (!provider) {
      STATE.ok = false;
      STATE.connected = false;
      STATE.error = "MetaMask not found. Install MetaMask to continue.";
      _emitUpdate("connect:missing");
      return { ok: false, error: STATE.error };
    }
    try {
      const accounts = await provider.request({ method: "eth_requestAccounts" });
      const chainHex = await provider.request({ method: "eth_chainId" });
      const addr = (accounts && accounts[0]) ? String(accounts[0]).toLowerCase() : "";
      STATE.ok = true;
      STATE.connected = true;
      STATE.address = addr;
      STATE.chainId = hexToInt(chainHex);
      STATE.error = "";
      _subscribe(provider);
      _emitUpdate("connect:ok");
      return {
        ok: true,
        address: addr,
        chainId: STATE.chainId,
        providerName: STATE.providerName
      };
    } catch (err) {
      const msg = err && err.message ? err.message : String(err);
      STATE.ok = false;
      STATE.error = msg;
      _emitUpdate("connect:error");
      return { ok: false, error: msg };
    }
  }

  async function switchToSepolia() {
    const provider = _ethProvider();
    if (!provider) {
      return { ok: false, error: "MetaMask not found." };
    }
    try {
      await provider.request({
        method: "wallet_switchEthereumChain",
        params: [{ chainId: SEPOLIA_HEX }]
      });
      const chainHex = await provider.request({ method: "eth_chainId" });
      STATE.chainId = hexToInt(chainHex);
      _emitUpdate("switch:ok");
      return { ok: true, chainId: STATE.chainId };
    } catch (err) {
      // 4902 = chain not added yet
      if (err && err.code === 4902) {
        try {
          await provider.request({
            method: "wallet_addEthereumChain",
            params: [{
              chainId: SEPOLIA_HEX,
              chainName: "Sepolia",
              nativeCurrency: { name: "Sepolia ETH", symbol: "ETH", decimals: 18 },
              rpcUrls: ["https://rpc.sepolia.org"],
              blockExplorerUrls: ["https://sepolia.etherscan.io"]
            }]
          });
          STATE.chainId = SEPOLIA_INT;
          _emitUpdate("switch:added");
          return { ok: true, chainId: SEPOLIA_INT };
        } catch (addErr) {
          const msg = addErr && addErr.message ? addErr.message : String(addErr);
          return { ok: false, error: msg };
        }
      }
      const msg = err && err.message ? err.message : String(err);
      return { ok: false, error: msg };
    }
  }

  // ------------------------------------------------------------------
  // runAction — map UI action key to a real ethers contract call
  // ------------------------------------------------------------------
  async function runAction(actionKey, opts) {
    opts = opts || {};
    const contractName = opts.contract;
    const address = opts.address;
    const func = opts.func;
    const provider = _ethProvider();

    if (!provider) {
      return { ok: false, error: "MetaMask not found." };
    }
    if (!address || !address.startsWith("0x")) {
      return {
        ok: false,
        error: "No deployment address for " + contractName +
               " — fill contracts/deployments/sepolia.json and reload."
      };
    }

    let ethers;
    try { ethers = await loadEthers(); }
    catch (e) { return { ok: false, error: e.message || String(e) }; }

    const abi = ABI[contractName];
    if (!abi) {
      return { ok: false, error: "No ABI loaded for " + contractName };
    }
    const argPack = (DEMO_ARGS[actionKey] || (() => ({ args: [] })))();
    const runtimeArgs = Array.isArray(opts.args) ? opts.args : null;
    const runtimeValue = opts.value != null ? opts.value : null;

    try {
      const ethProv = new ethers.BrowserProvider(provider);
      const signer = await ethProv.getSigner();
      const chainHex = await provider.request({ method: "eth_chainId" });
      if (hexToInt(chainHex) !== SEPOLIA_INT) {
        return {
          ok: false,
          error: "Wallet is not on Sepolia — switch network before signing."
        };
      }
      const contract = new ethers.Contract(address, abi, signer);
      if (typeof contract[func] !== "function") {
        return { ok: false, error: "Function " + func + " not in ABI for " + contractName };
      }
      const effectiveValue = runtimeValue != null ? runtimeValue : argPack.value;
      const overrides = effectiveValue ? { value: effectiveValue } : {};
      const args = runtimeArgs || argPack.args || [];
      const tx = await contract[func](...args, overrides);
      (async () => {
        try {
          await tx.wait();
          window.__aequitasLastConfirmedTx = tx.hash;
          window.dispatchEvent(new CustomEvent("aequitas:tx", {
            detail: { hash: tx.hash, confirmed: true }
          }));
        } catch (waitErr) {
          console.warn("[aequitas] tx confirmation wait failed:", waitErr);
        }
      })();
      return { ok: true, hash: tx.hash, confirmed: false };
    } catch (err) {
      const msg = (err && (err.shortMessage || err.message)) || String(err);
      return { ok: false, error: msg };
    }
  }

  function getState() {
    return _snapshot();
  }

  // ------------------------------------------------------------------
  // Expose
  // ------------------------------------------------------------------
  _discover();
  // Give any provider a beat to announce before we pick one.
  setTimeout(_pickProvider, 150);

  window.aequitasWallet = {
    connect,
    switchToSepolia,
    runAction,
    hasEthereum,
    getState,
    SEPOLIA_INT,
    _pickProvider,
    forceMetaMask,
    _state: STATE
  };

  // Soft breadcrumb for the console so devs can see the bridge is live.
  try {
    setTimeout(() => {
      const picked = _pickProvider();
      console.log("[aequitas] wallet bridge loaded · provider:",
        picked ? (picked.info.name || picked.info.rdns) : "missing");
    }, 50);
  } catch (_) {}
})();
