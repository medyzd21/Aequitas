// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {IStressOracle} from "./interfaces/IStressOracle.sol";
import {Owned} from "./utils/Owned.sol";
import {Roles} from "./utils/Roles.sol";

/**
 * @title StressOracle — on-chain mirror of the off-chain stress signal
 *        produced by Python (Astra).
 * @notice Python Monte-Carlo runs (engine.fairness_stress + engine.simulation)
 *         produce a single normalised stress level in [0, 1]. The reporter
 *         pushes that level + a reasonCode + a hash of the underlying data
 *         so the on-chain record is auditable.
 *
 *         BackstopVault reads `stressLevel()` to decide whether to release
 *         reserves.
 */
contract StressOracle is IStressOracle, Roles {
    bytes32 public constant REPORTER_ROLE = keccak256("REPORTER_ROLE");

    uint256 public stressLevel;
    uint64 public lastUpdate;
    bytes32 public lastReason;
    bytes32 public lastDataHash;

    uint256 public constant MAX_LEVEL = 1e18;

    error LevelOutOfRange(uint256 level);

    constructor(address initialOwner) Owned(initialOwner) {}

    function updateStressLevel(uint256 level, bytes32 reasonCode, bytes32 dataHash)
        external
        onlyRole(REPORTER_ROLE)
    {
        if (level > MAX_LEVEL) revert LevelOutOfRange(level);
        stressLevel = level;
        lastUpdate = uint64(block.timestamp);
        lastReason = reasonCode;
        lastDataHash = dataHash;
        emit StressLevelUpdated(level, reasonCode, dataHash);
    }
}
