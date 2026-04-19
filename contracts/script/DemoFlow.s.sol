// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Script, console2} from "forge-std/Script.sol";

import {CohortLedger}    from "../src/CohortLedger.sol";
import {FairnessGate}    from "../src/FairnessGate.sol";
import {MortalityOracle} from "../src/MortalityOracle.sol";
import {LongevaPool}     from "../src/LongevaPool.sol";
import {BenefitStreamer} from "../src/BenefitStreamer.sol";
import {VestaRouter}     from "../src/VestaRouter.sol";
import {StressOracle}    from "../src/StressOracle.sol";
import {BackstopVault}   from "../src/BackstopVault.sol";

/**
 * @title DemoFlow — capstone walk-through against a deployed stack.
 * @notice Reads the addresses written by Deploy.s.sol at
 *         `deployments/latest.txt`, then replays the Aequitas story end
 *         to end — register members, contribute, set baseline, submit a
 *         proposal, seed the pool, open a retirement, push a stress
 *         update, and release a small backstop. Every step prints so
 *         the viewer can follow what each contract is doing.
 *
 *         Run this AFTER Deploy.s.sol:
 *
 *             forge script script/DemoFlow.s.sol \
 *                 --rpc-url localhost              \
 *                 --private-key $ANVIL_PK          \
 *                 --broadcast
 *
 *         Because the broadcasting EOA inherits every role from the
 *         deploy script, it can register members, push stress, act as
 *         guardian, and so on — that would never be true on Sepolia,
 *         but it keeps the local demo to a single transaction sender.
 */
contract DemoFlow is Script {
    // demo members ------------------------------------------------------------
    address constant ALICE = address(0xA11CE);   // born 1960, retires now
    address constant BOB   = address(0xB0B);     // born 1995, accumulating

    function run() external {
        // Addresses from latest deploy -------------------------------------
        CohortLedger    ledger    = CohortLedger(_readAddr("CohortLedger"));
        FairnessGate    gate      = FairnessGate(_readAddr("FairnessGate"));
        MortalityOracle mortality = MortalityOracle(_readAddr("MortalityOracle"));
        LongevaPool     pool      = LongevaPool(payable(_readAddr("LongevaPool")));
        BenefitStreamer streamer  = BenefitStreamer(payable(_readAddr("BenefitStreamer")));
        VestaRouter     router    = VestaRouter(payable(_readAddr("VestaRouter")));
        StressOracle    stress    = StressOracle(_readAddr("StressOracle"));
        BackstopVault   vault     = BackstopVault(payable(_readAddr("BackstopVault")));

        vm.startBroadcast();

        // 1) EquiGen: register members and contribute ----------------------
        console2.log("--- EquiGen: register + contribute ---");
        ledger.registerMember(ALICE, 1960);
        ledger.registerMember(BOB,   1995);
        ledger.contribute(ALICE, 100e18);
        ledger.contribute(BOB,    20e18);
        console2.log("alice PIUs:", ledger.getMember(ALICE).piuBalance);
        console2.log("bob PIUs:  ", ledger.getMember(BOB).piuBalance);

        // 2) EquiGen: baseline + a balanced proposal -----------------------
        console2.log("--- EquiGen: baseline + proposal ---");
        uint16[] memory cohorts = new uint16[](2);
        cohorts[0] = 1960;
        cohorts[1] = 1995;
        int256[] memory epvs = new int256[](2);
        epvs[0] = 100e18;
        epvs[1] = 100e18;
        gate.setBaseline(cohorts, epvs);

        int256[] memory newEpvs = new int256[](2);
        newEpvs[0] = 101e18;
        newEpvs[1] = 101e18;
        (, bool passes) = gate.submitAndEvaluate("balanced +1%", cohorts, newEpvs, 0.05e18);
        console2.log("proposal passes:", passes);

        // 3) Longeva: seed the pool then mark Alice retired ----------------
        console2.log("--- Longeva: deposit + retire ---");
        pool.deposit{value: 30 ether}(ALICE, 30 ether);
        ledger.markRetired(ALICE);
        console2.log("pool totalAssets:", pool.totalAssets());

        // 4) Vesta: open Alice's retirement stream -------------------------
        console2.log("--- Vesta: open retirement ---");
        router.openRetirement(ALICE, 10 ether, uint128(12 ether), 0);
        console2.log("streamer fundedBalance:", streamer.fundedBalance());

        // 5) Astra: seed backstop, push stress, release --------------------
        console2.log("--- Astra: stress + backstop ---");
        vault.deposit{value: 5 ether}();
        stress.updateStressLevel(0.82e18, bytes32("p95_gini>threshold"), bytes32(0));
        vault.release(0.5 ether);
        console2.log("backstop totalReleased:", vault.totalReleased());
        console2.log("stress level:         ", stress.stressLevel());

        // 6) Longeva: mortality credit for a deceased member (simulated) ---
        console2.log("--- Longeva: mortality credit ---");
        mortality.confirmDeath(BOB, uint64(block.timestamp), bytes32("cert-bob"));
        // Bob had no pool shares in this demo — credit call would revert.
        // Keep the confirm so the downstream streamer halt is visible.
        console2.log("bob deceased:", mortality.isDeceased(BOB));

        vm.stopBroadcast();

        console2.log("=== DemoFlow complete ===");
    }

    // ------------------------------------------------------------ helpers
    /// @dev Parse `deployments/latest.txt` for a single contract address.
    ///      Keeps the script dependency-free at the cost of a tiny parser.
    function _readAddr(string memory name) internal view returns (address) {
        string memory file = vm.readFile("deployments/latest.txt");
        string memory needle = string.concat(name, "=0x");
        bytes memory raw = bytes(file);
        bytes memory n = bytes(needle);

        for (uint256 i = 0; i + n.length <= raw.length; i++) {
            bool ok = true;
            for (uint256 j = 0; j < n.length; j++) {
                if (raw[i + j] != n[j]) { ok = false; break; }
            }
            if (ok) {
                // address is 42 chars starting at i + name.length + 1
                bytes memory addrHex = new bytes(42);
                for (uint256 k = 0; k < 42; k++) {
                    addrHex[k] = raw[i + bytes(name).length + 1 + k];
                }
                return vm.parseAddress(string(addrHex));
            }
        }
        revert(string.concat("deployments/latest.txt missing key: ", name));
    }
}
