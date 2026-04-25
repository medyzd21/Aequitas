// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

interface IActuarialResultRegistry {
    struct ParameterSet {
        bytes32 parameterSetKey;
        uint64 valuationDate;
        int32 discountRateBps;
        int32 salaryGrowthBps;
        int32 investmentReturnBps;
        uint256 piuPrice;
        uint32 fairnessDeltaBps;
        uint64 mortalityBasisVersion;
        bytes32 parameterHash;
        address publisher;
    }

    struct ValuationSnapshot {
        bytes32 valuationSnapshotKey;
        bytes32 parameterSetKey;
        bytes32 memberSnapshotHash;
        bytes32 cohortSummaryHash;
        uint64 memberCount;
        uint32 cohortCount;
        bytes32 inputHash;
        address publisher;
    }

    struct SchemeSummary {
        bytes32 schemeSummaryKey;
        bytes32 valuationSnapshotKey;
        uint256 epvContributions;
        uint256 epvBenefits;
        uint256 mwrBps;
        uint256 fundedRatioBps;
        bytes32 summaryHash;
        address publisher;
    }

    struct CohortSummary {
        bytes32 cohortSummaryKey;
        bytes32 valuationSnapshotKey;
        uint16 cohort;
        uint256 epvContributions;
        uint256 epvBenefits;
        uint256 mwrBps;
        uint32 members;
        bytes32 summaryHash;
        address publisher;
    }

    struct ResultBundle {
        bytes32 resultBundleKey;
        bytes32 parameterSetKey;
        bytes32 valuationSnapshotKey;
        bytes32 mortalityMethodKey;
        bytes32 epvMethodKey;
        bytes32 mwrMethodKey;
        bytes32 fairnessMethodKey;
        bytes32 schemeSummaryKey;
        bytes32 cohortDigest;
        bytes32 resultHash;
        address publisher;
    }

    event ParameterSetPublished(bytes32 indexed parameterSetKey, uint64 valuationDate, bytes32 parameterHash, address indexed publisher);
    event ValuationSnapshotPublished(bytes32 indexed valuationSnapshotKey, bytes32 indexed parameterSetKey, bytes32 inputHash, address indexed publisher);
    event SchemeSummaryPublished(bytes32 indexed schemeSummaryKey, bytes32 indexed valuationSnapshotKey, bytes32 summaryHash, address indexed publisher);
    event CohortSummaryPublished(bytes32 indexed cohortSummaryKey, uint16 indexed cohort, bytes32 summaryHash, address indexed publisher);
    event ResultBundlePublished(bytes32 indexed resultBundleKey, bytes32 indexed valuationSnapshotKey, bytes32 resultHash, address indexed publisher);

    function getParameterSet(bytes32 parameterSetKey) external view returns (ParameterSet memory);
    function getValuationSnapshot(bytes32 valuationSnapshotKey) external view returns (ValuationSnapshot memory);
    function getSchemeSummary(bytes32 schemeSummaryKey) external view returns (SchemeSummary memory);
    function getCohortSummary(bytes32 cohortSummaryKey) external view returns (CohortSummary memory);
    function getResultBundle(bytes32 resultBundleKey) external view returns (ResultBundle memory);
}
