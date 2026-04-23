// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

interface IMortalityBasisOracle {
    struct BasisSnapshot {
        uint64 version;
        bytes32 baselineId;
        bytes32 cohortDigest;
        uint32 credibilityBps;
        uint64 effectiveDate;
        bytes32 studyHash;
        uint64 exposureScaled;
        uint32 observedDeaths;
        uint64 expectedDeathsScaled;
        address publisher;
        bool advisory;
    }

    event MortalityBasisPublished(
        uint64 indexed version,
        bytes32 indexed baselineId,
        bytes32 cohortDigest,
        uint32 credibilityBps,
        uint64 effectiveDate,
        bytes32 studyHash,
        address indexed publisher,
        bool advisory
    );

    function latestVersion() external view returns (uint64);

    function currentBasis() external view returns (BasisSnapshot memory);

    function basisOf(uint64 version) external view returns (BasisSnapshot memory);
}
