// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @notice The off-chain Python stress simulator (engine.fairness_stress +
///         engine.simulation) pushes a normalised stress level here. All
///         on-chain modules read `stressLevel()`.
interface IStressOracle {
    /// @param level 0..1e18 fixed-point. 0 = benign; 1e18 = critical.
    event StressLevelUpdated(uint256 level, bytes32 reasonCode, bytes32 dataHash);

    function stressLevel() external view returns (uint256);
    function lastUpdate() external view returns (uint64);
    function updateStressLevel(uint256 level, bytes32 reasonCode, bytes32 dataHash) external;
}
