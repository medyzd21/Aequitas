// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {IMortalityBasisOracle} from "./interfaces/IMortalityBasisOracle.sol";
import {Owned} from "./utils/Owned.sol";
import {Roles} from "./utils/Roles.sol";

/**
 * @title MortalityBasisOracle
 * @notice Publishes compact, versioned mortality basis snapshots.
 *
 * Raw death records, birthdates, health data, and actuarial calibration
 * internals stay off-chain. This contract stores only the publishable
 * audit surface:
 *
 * - basis version id
 * - baseline model identifier
 * - cohort digest
 * - credibility score
 * - effective date
 * - study hash
 * - compact study summary counts
 * - publisher address
 *
 * The goal is not to fit mortality on chain. The goal is to timestamp
 * which aggregate assumption set was active when downstream valuations,
 * fairness publications, or reserve decisions were made.
 */
contract MortalityBasisOracle is IMortalityBasisOracle, Roles {
    bytes32 public constant PUBLISHER_ROLE = keccak256("PUBLISHER_ROLE");

    uint64 public latestVersion;
    mapping(uint64 => BasisSnapshot) private _basis;

    error InvalidParams();
    error VersionAlreadyExists(uint64 version);
    error VersionOutOfOrder(uint64 latest, uint64 attempted);

    constructor(address initialOwner) Owned(initialOwner) {}

    function publishBasis(
        uint64 version,
        bytes32 baselineId,
        bytes32 cohortDigest,
        uint32 credibilityBps,
        uint64 effectiveDate,
        bytes32 studyHash,
        uint64 exposureScaled,
        uint32 observedDeaths,
        uint64 expectedDeathsScaled,
        bool advisory
    ) external onlyRole(PUBLISHER_ROLE) {
        if (version == 0) revert InvalidParams();
        if (_basis[version].version != 0) revert VersionAlreadyExists(version);
        if (version <= latestVersion) revert VersionOutOfOrder(latestVersion, version);
        if (credibilityBps > 10_000) revert InvalidParams();

        BasisSnapshot memory snap = BasisSnapshot({
            version: version,
            baselineId: baselineId,
            cohortDigest: cohortDigest,
            credibilityBps: credibilityBps,
            effectiveDate: effectiveDate,
            studyHash: studyHash,
            exposureScaled: exposureScaled,
            observedDeaths: observedDeaths,
            expectedDeathsScaled: expectedDeathsScaled,
            publisher: msg.sender,
            advisory: advisory
        });

        _basis[version] = snap;
        latestVersion = version;

        emit MortalityBasisPublished(
            version,
            baselineId,
            cohortDigest,
            credibilityBps,
            effectiveDate,
            studyHash,
            msg.sender,
            advisory
        );
    }

    function currentBasis() external view returns (BasisSnapshot memory) {
        return _basis[latestVersion];
    }

    function basisOf(uint64 version) external view returns (BasisSnapshot memory) {
        return _basis[version];
    }
}
