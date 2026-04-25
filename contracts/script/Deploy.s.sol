// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Script, console2} from "forge-std/Script.sol";

import {CohortLedger}    from "../src/CohortLedger.sol";
import {FairnessGate}    from "../src/FairnessGate.sol";
import {MortalityOracle} from "../src/MortalityOracle.sol";
import {MortalityBasisOracle} from "../src/MortalityBasisOracle.sol";
import {InvestmentPolicyBallot} from "../src/InvestmentPolicyBallot.sol";
import {ActuarialMethodRegistry} from "../src/ActuarialMethodRegistry.sol";
import {ActuarialResultRegistry} from "../src/ActuarialResultRegistry.sol";
import {ActuarialVerifier} from "../src/ActuarialVerifier.sol";
import {LongevaPool}     from "../src/LongevaPool.sol";
import {BenefitStreamer} from "../src/BenefitStreamer.sol";
import {VestaRouter}     from "../src/VestaRouter.sol";
import {StressOracle}    from "../src/StressOracle.sol";
import {BackstopVault}   from "../src/BackstopVault.sol";

import {ICohortLedger}    from "../src/interfaces/ICohortLedger.sol";
import {IMortalityOracle} from "../src/interfaces/IMortalityOracle.sol";
import {ILongevaPool}     from "../src/interfaces/ILongevaPool.sol";
import {IStressOracle}    from "../src/interfaces/IStressOracle.sol";

/**
 * @title Deploy — one-shot deployment for the full Aequitas hybrid stack.
 * @author Aequitas
 * @notice Deploys the full protocol stack, including the actuarial proof layer,
 *         and wires the role graph so the system is
 *         executable end-to-end out of the box. Intended for local Anvil
 *         or Sepolia.
 *
 *         Usage (local):
 *             anvil &                            # in another terminal
 *             forge script script/Deploy.s.sol \
 *                 --rpc-url localhost            \
 *                 --private-key $ANVIL_PK        \
 *                 --broadcast
 *
 *         Usage (Sepolia):
 *             cp .env.example .env && fill in keys
 *             source .env
 *             forge script script/Deploy.s.sol  \
 *                 --rpc-url sepolia             \
 *                 --private-key $DEPLOYER_PK    \
 *                 --broadcast --verify
 *
 *         After deployment the addresses are printed to stdout and also
 *         written to `deployments/latest.txt` so the Python bridge can pick
 *         them up.
 */
contract Deploy is Script {
    // tunable actuarial + safety parameters ----------------------------------
    uint256 constant PIU_PRICE           = 1e18;   // 1 currency unit = 1 PIU
    uint256 constant STRESS_RELEASE_BP   = 7e17;   // release reserves when stress ≥ 0.7
    uint256 constant PER_CALL_CAP_BPS    = 5_000;  // release at most 50% per call

    // role ids (keccak of string) --------------------------------------------
    bytes32 constant REGISTRAR_ROLE    = keccak256("REGISTRAR_ROLE");
    bytes32 constant CONTRIBUTION_ROLE = keccak256("CONTRIBUTION_ROLE");
    bytes32 constant RETIREMENT_ROLE   = keccak256("RETIREMENT_ROLE");
    bytes32 constant BASELINE_ROLE     = keccak256("BASELINE_ROLE");
    bytes32 constant PROPOSER_ROLE     = keccak256("PROPOSER_ROLE");
    bytes32 constant ORACLE_ROLE       = keccak256("ORACLE_ROLE");
    bytes32 constant PUBLISHER_ROLE    = keccak256("PUBLISHER_ROLE");
    bytes32 constant BALLOT_ADMIN_ROLE = keccak256("BALLOT_ADMIN_ROLE");
    bytes32 constant SNAPSHOT_ROLE     = keccak256("SNAPSHOT_ROLE");
    bytes32 constant METHOD_ADMIN_ROLE = keccak256("METHOD_ADMIN_ROLE");
    bytes32 constant DEPOSIT_ROLE      = keccak256("DEPOSIT_ROLE");
    bytes32 constant PAYOUT_ROLE       = keccak256("PAYOUT_ROLE");
    bytes32 constant YIELD_ROLE        = keccak256("YIELD_ROLE");
    bytes32 constant STREAM_ADMIN_ROLE = keccak256("STREAM_ADMIN_ROLE");
    bytes32 constant FUNDER_ROLE       = keccak256("FUNDER_ROLE");
    bytes32 constant OPERATOR_ROLE     = keccak256("OPERATOR_ROLE");
    bytes32 constant REPORTER_ROLE     = keccak256("REPORTER_ROLE");
    bytes32 constant GUARDIAN_ROLE     = keccak256("GUARDIAN_ROLE");
    bytes32 constant DEPOSITOR_ROLE    = keccak256("DEPOSITOR_ROLE");

    // deployed addresses -----------------------------------------------------
    CohortLedger    public cohortLedger;
    FairnessGate    public fairnessGate;
    MortalityOracle public mortalityOracle;
    MortalityBasisOracle public mortalityBasisOracle;
    InvestmentPolicyBallot public investmentPolicyBallot;
    ActuarialMethodRegistry public actuarialMethodRegistry;
    ActuarialResultRegistry public actuarialResultRegistry;
    ActuarialVerifier public actuarialVerifier;
    LongevaPool     public longevaPool;
    BenefitStreamer public benefitStreamer;
    VestaRouter     public vestaRouter;
    StressOracle    public stressOracle;
    BackstopVault   public backstopVault;

    function run() external {
        // Owner / operator address. In a real deploy this is the Gnosis Safe
        // or governance multisig. For local demos it's the broadcasting EOA.
        address owner = msg.sender;

        // Optional dedicated reporter / guardian / operator. Defaults to the
        // same EOA for a dev-mode deploy; override via `env DEPLOY_*=0x…`.
        address reporter  = _envOrDefault("DEPLOY_REPORTER",  owner);
        address guardian  = _envOrDefault("DEPLOY_GUARDIAN",  owner);
        address operator  = _envOrDefault("DEPLOY_OPERATOR",  owner);
        address depositor = _envOrDefault("DEPLOY_DEPOSITOR", owner);

        vm.startBroadcast();

        // --- Phase A: EquiGen ------------------------------------------------
        cohortLedger = new CohortLedger(owner, PIU_PRICE);
        fairnessGate = new FairnessGate(owner);

        // --- Phase B: Longeva ------------------------------------------------
        mortalityOracle = new MortalityOracle(owner);
        mortalityBasisOracle = new MortalityBasisOracle(owner);
        investmentPolicyBallot = new InvestmentPolicyBallot(owner);
        actuarialMethodRegistry = new ActuarialMethodRegistry(owner);
        actuarialResultRegistry = new ActuarialResultRegistry(owner);
        actuarialVerifier = new ActuarialVerifier();
        longevaPool     = new LongevaPool(owner, IMortalityOracle(address(mortalityOracle)));

        // --- Phase C: Vesta --------------------------------------------------
        benefitStreamer = new BenefitStreamer(owner, IMortalityOracle(address(mortalityOracle)));
        vestaRouter     = new VestaRouter(
            owner,
            ICohortLedger(address(cohortLedger)),
            ILongevaPool(address(longevaPool)),
            benefitStreamer
        );

        // --- Phase D: Astra --------------------------------------------------
        stressOracle  = new StressOracle(owner);
        // Beneficiary of the backstop is BenefitStreamer (so releases top up
        // retiree streams directly).
        backstopVault = new BackstopVault(
            owner,
            IStressOracle(address(stressOracle)),
            address(benefitStreamer),
            STRESS_RELEASE_BP,
            PER_CALL_CAP_BPS
        );

        // ---------------------------------------------------------- role wiring
        // CohortLedger roles
        cohortLedger.grantRole(REGISTRAR_ROLE,    owner);
        cohortLedger.grantRole(CONTRIBUTION_ROLE, owner);
        cohortLedger.grantRole(RETIREMENT_ROLE,   owner);

        // FairnessGate roles
        fairnessGate.grantRole(BASELINE_ROLE, owner);
        fairnessGate.grantRole(PROPOSER_ROLE, owner);

        // MortalityOracle
        mortalityOracle.grantRole(ORACLE_ROLE, reporter);
        mortalityBasisOracle.grantRole(PUBLISHER_ROLE, reporter);
        investmentPolicyBallot.grantRole(BALLOT_ADMIN_ROLE, operator);
        investmentPolicyBallot.grantRole(SNAPSHOT_ROLE, reporter);
        actuarialMethodRegistry.grantRole(METHOD_ADMIN_ROLE, reporter);
        actuarialResultRegistry.grantRole(PUBLISHER_ROLE, reporter);

        // LongevaPool roles — VestaRouter is the PAYOUT_ROLE so it can pull
        // funding when opening a retirement.
        longevaPool.grantRole(DEPOSIT_ROLE, depositor);
        longevaPool.grantRole(PAYOUT_ROLE,  address(vestaRouter));
        longevaPool.grantRole(YIELD_ROLE,   owner);

        // BenefitStreamer — VestaRouter drives both admin and funding.
        benefitStreamer.grantRole(STREAM_ADMIN_ROLE, address(vestaRouter));
        benefitStreamer.grantRole(FUNDER_ROLE,       address(vestaRouter));

        // VestaRouter operator
        vestaRouter.grantRole(OPERATOR_ROLE, operator);

        // Astra
        stressOracle.grantRole(REPORTER_ROLE, reporter);
        backstopVault.grantRole(GUARDIAN_ROLE,  guardian);
        backstopVault.grantRole(DEPOSITOR_ROLE, depositor);

        vm.stopBroadcast();

        // Summary --------------------------------------------------------------
        console2.log("=== Aequitas deployment ===");
        console2.log("owner            ", owner);
        console2.log("CohortLedger     ", address(cohortLedger));
        console2.log("FairnessGate     ", address(fairnessGate));
        console2.log("MortalityOracle  ", address(mortalityOracle));
        console2.log("MortalityBasisOracle", address(mortalityBasisOracle));
        console2.log("InvestmentPolicyBallot", address(investmentPolicyBallot));
        console2.log("ActuarialMethodRegistry", address(actuarialMethodRegistry));
        console2.log("ActuarialResultRegistry", address(actuarialResultRegistry));
        console2.log("ActuarialVerifier", address(actuarialVerifier));
        console2.log("LongevaPool      ", address(longevaPool));
        console2.log("BenefitStreamer  ", address(benefitStreamer));
        console2.log("VestaRouter      ", address(vestaRouter));
        console2.log("StressOracle     ", address(stressOracle));
        console2.log("BackstopVault    ", address(backstopVault));

        _writeLatest(owner);
    }

    // ----------------------------------------------------------- helpers
    function _envOrDefault(string memory key, address fallback_) internal view returns (address) {
        try vm.envAddress(key) returns (address a) {
            if (a != address(0)) return a;
        } catch {}
        return fallback_;
    }

    /// @dev Persist deployed addresses so the Python bridge and the README
    /// smoke tests can pick them up without parsing stdout.
    function _writeLatest(address owner) internal {
        string memory out = string.concat(
            "owner=",           vm.toString(owner),                    "\n",
            "CohortLedger=",    vm.toString(address(cohortLedger)),    "\n",
            "FairnessGate=",    vm.toString(address(fairnessGate)),    "\n",
            "MortalityOracle=", vm.toString(address(mortalityOracle)), "\n",
            "MortalityBasisOracle=", vm.toString(address(mortalityBasisOracle)), "\n",
            "InvestmentPolicyBallot=", vm.toString(address(investmentPolicyBallot)), "\n",
            "ActuarialMethodRegistry=", vm.toString(address(actuarialMethodRegistry)), "\n",
            "ActuarialResultRegistry=", vm.toString(address(actuarialResultRegistry)), "\n",
            "ActuarialVerifier=", vm.toString(address(actuarialVerifier)), "\n",
            "LongevaPool=",     vm.toString(address(longevaPool)),     "\n",
            "BenefitStreamer=", vm.toString(address(benefitStreamer)), "\n",
            "VestaRouter=",     vm.toString(address(vestaRouter)),     "\n",
            "StressOracle=",    vm.toString(address(stressOracle)),    "\n",
            "BackstopVault=",   vm.toString(address(backstopVault)),   "\n"
        );
        try vm.writeFile("deployments/latest.txt", out) {} catch {}
    }
}
