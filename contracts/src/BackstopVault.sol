// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {IStressOracle} from "./interfaces/IStressOracle.sol";
import {Owned} from "./utils/Owned.sol";
import {Roles} from "./utils/Roles.sol";

/**
 * @title BackstopVault — Astra reserve.
 * @notice Accumulates a reserve (seeded by the operator, the protocol, or
 *         DAO treasury). When the StressOracle reports a level above the
 *         release threshold, a GUARDIAN role can release reserves to a
 *         preconfigured beneficiary (typically BenefitStreamer or
 *         LongevaPool) up to a per-call cap.
 *
 *         The size of the backstop is computed OFF-CHAIN by the Python
 *         stress module (see `engine.fairness_stress.stochastic_cohort_stress`
 *         and `engine.simulation.simulate_fund`). That module outputs the
 *         expected shortfall / p95 gap, and governance deposits that amount
 *         here. On-chain, we only execute release rules.
 */
contract BackstopVault is Roles {
    bytes32 public constant GUARDIAN_ROLE = keccak256("GUARDIAN_ROLE");
    bytes32 public constant DEPOSITOR_ROLE = keccak256("DEPOSITOR_ROLE");

    IStressOracle public immutable stressOracle;
    address public beneficiary;

    /// @dev Stress level ≥ `releaseThreshold` permits a release.
    uint256 public releaseThreshold;       // 1e18-scaled
    uint256 public perCallCapBps;          // basis points of current reserve; 10_000 = 100%
    uint256 public totalDeposited;
    uint256 public totalReleased;

    bool private _entered; // reentrancy guard

    event BeneficiaryUpdated(address indexed newBeneficiary);
    event ParametersUpdated(uint256 releaseThreshold, uint256 perCallCapBps);
    event Deposited(address indexed from, uint256 amount);
    event Released(address indexed to, uint256 amount, uint256 stressLevel);

    error Reentrancy();
    error StressBelowThreshold(uint256 current, uint256 threshold);
    error ZeroReserve();
    error CapExceeded(uint256 requested, uint256 cap);
    error InvalidParams();

    modifier nonReentrant() {
        if (_entered) revert Reentrancy();
        _entered = true;
        _;
        _entered = false;
    }

    constructor(
        address initialOwner,
        IStressOracle _stressOracle,
        address _beneficiary,
        uint256 _releaseThreshold,
        uint256 _perCallCapBps
    ) Owned(initialOwner) {
        if (address(_stressOracle) == address(0) || _beneficiary == address(0)) revert ZeroAddress();
        if (_perCallCapBps > 10_000 || _releaseThreshold > 1e18) revert InvalidParams();
        stressOracle = _stressOracle;
        beneficiary = _beneficiary;
        releaseThreshold = _releaseThreshold;
        perCallCapBps = _perCallCapBps;
    }

    // ----------------------------------------------------------- admin
    function setBeneficiary(address newBeneficiary) external onlyOwner {
        if (newBeneficiary == address(0)) revert ZeroAddress();
        beneficiary = newBeneficiary;
        emit BeneficiaryUpdated(newBeneficiary);
    }

    function setParameters(uint256 newThreshold, uint256 newCapBps) external onlyOwner {
        if (newCapBps > 10_000 || newThreshold > 1e18) revert InvalidParams();
        releaseThreshold = newThreshold;
        perCallCapBps = newCapBps;
        emit ParametersUpdated(newThreshold, newCapBps);
    }

    // -------------------------------------------------------- deposits
    function deposit() external payable onlyRole(DEPOSITOR_ROLE) {
        totalDeposited += msg.value;
        emit Deposited(msg.sender, msg.value);
    }

    // -------------------------------------------------------- release
    function release(uint256 amount) external onlyRole(GUARDIAN_ROLE) nonReentrant {
        uint256 level = stressOracle.stressLevel();
        if (level < releaseThreshold) revert StressBelowThreshold(level, releaseThreshold);

        uint256 reserve = address(this).balance;
        if (reserve == 0) revert ZeroReserve();

        uint256 cap = (reserve * perCallCapBps) / 10_000;
        if (amount > cap) revert CapExceeded(amount, cap);

        totalReleased += amount;
        (bool ok, ) = payable(beneficiary).call{value: amount}("");
        require(ok, "release fail");
        emit Released(beneficiary, amount, level);
    }

    function reserve() external view returns (uint256) {
        return address(this).balance;
    }

    receive() external payable {
        totalDeposited += msg.value;
        emit Deposited(msg.sender, msg.value);
    }
}
