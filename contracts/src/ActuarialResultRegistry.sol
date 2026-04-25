// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {IActuarialResultRegistry} from "./interfaces/IActuarialResultRegistry.sol";
import {Owned} from "./utils/Owned.sol";
import {Roles} from "./utils/Roles.sol";

/**
 * @title ActuarialResultRegistry
 * @notice Append-only registry for actuarial parameter/input/result commitments.
 *
 * The chain stores publishable commitments and compact summary metrics, not the
 * full actuarial engine inputs. Raw member data, full cashflow vectors, and
 * calibration internals remain off-chain.
 */
contract ActuarialResultRegistry is IActuarialResultRegistry, Roles {
    bytes32 public constant PUBLISHER_ROLE = keccak256("PUBLISHER_ROLE");

    mapping(bytes32 => ParameterSet) private _parameterSets;
    mapping(bytes32 => ValuationSnapshot) private _valuationSnapshots;
    mapping(bytes32 => SchemeSummary) private _schemeSummaries;
    mapping(bytes32 => CohortSummary) private _cohortSummaries;
    mapping(bytes32 => ResultBundle) private _resultBundles;

    error InvalidParams();
    error AlreadyPublished(bytes32 key);

    constructor(address initialOwner) Owned(initialOwner) {}

    function publishParameterSet(
        bytes32 parameterSetKey,
        uint64 valuationDate,
        int32 discountRateBps,
        int32 salaryGrowthBps,
        int32 investmentReturnBps,
        uint256 piuPrice,
        uint32 fairnessDeltaBps,
        uint64 mortalityBasisVersion,
        bytes32 parameterHash
    ) external onlyRole(PUBLISHER_ROLE) {
        if (parameterSetKey == bytes32(0) || parameterHash == bytes32(0)) revert InvalidParams();
        if (_parameterSets[parameterSetKey].parameterSetKey != bytes32(0)) revert AlreadyPublished(parameterSetKey);
        _parameterSets[parameterSetKey] = ParameterSet({
            parameterSetKey: parameterSetKey,
            valuationDate: valuationDate,
            discountRateBps: discountRateBps,
            salaryGrowthBps: salaryGrowthBps,
            investmentReturnBps: investmentReturnBps,
            piuPrice: piuPrice,
            fairnessDeltaBps: fairnessDeltaBps,
            mortalityBasisVersion: mortalityBasisVersion,
            parameterHash: parameterHash,
            publisher: msg.sender
        });
        emit ParameterSetPublished(parameterSetKey, valuationDate, parameterHash, msg.sender);
    }

    function publishValuationSnapshot(
        bytes32 valuationSnapshotKey,
        bytes32 parameterSetKey,
        bytes32 memberSnapshotHash,
        bytes32 cohortSummaryHash,
        uint64 memberCount,
        uint32 cohortCount,
        bytes32 inputHash
    ) external onlyRole(PUBLISHER_ROLE) {
        if (
            valuationSnapshotKey == bytes32(0) ||
            parameterSetKey == bytes32(0) ||
            memberSnapshotHash == bytes32(0) ||
            cohortSummaryHash == bytes32(0) ||
            inputHash == bytes32(0)
        ) revert InvalidParams();
        if (_valuationSnapshots[valuationSnapshotKey].valuationSnapshotKey != bytes32(0)) {
            revert AlreadyPublished(valuationSnapshotKey);
        }
        _valuationSnapshots[valuationSnapshotKey] = ValuationSnapshot({
            valuationSnapshotKey: valuationSnapshotKey,
            parameterSetKey: parameterSetKey,
            memberSnapshotHash: memberSnapshotHash,
            cohortSummaryHash: cohortSummaryHash,
            memberCount: memberCount,
            cohortCount: cohortCount,
            inputHash: inputHash,
            publisher: msg.sender
        });
        emit ValuationSnapshotPublished(valuationSnapshotKey, parameterSetKey, inputHash, msg.sender);
    }

    function publishSchemeSummary(
        bytes32 schemeSummaryKey,
        bytes32 valuationSnapshotKey,
        uint256 epvContributions,
        uint256 epvBenefits,
        uint256 mwrBps,
        uint256 fundedRatioBps,
        bytes32 summaryHash
    ) external onlyRole(PUBLISHER_ROLE) {
        if (schemeSummaryKey == bytes32(0) || valuationSnapshotKey == bytes32(0) || summaryHash == bytes32(0)) revert InvalidParams();
        if (_schemeSummaries[schemeSummaryKey].schemeSummaryKey != bytes32(0)) revert AlreadyPublished(schemeSummaryKey);
        _schemeSummaries[schemeSummaryKey] = SchemeSummary({
            schemeSummaryKey: schemeSummaryKey,
            valuationSnapshotKey: valuationSnapshotKey,
            epvContributions: epvContributions,
            epvBenefits: epvBenefits,
            mwrBps: mwrBps,
            fundedRatioBps: fundedRatioBps,
            summaryHash: summaryHash,
            publisher: msg.sender
        });
        emit SchemeSummaryPublished(schemeSummaryKey, valuationSnapshotKey, summaryHash, msg.sender);
    }

    function publishCohortSummary(
        bytes32 cohortSummaryKey,
        bytes32 valuationSnapshotKey,
        uint16 cohort,
        uint256 epvContributions,
        uint256 epvBenefits,
        uint256 mwrBps,
        uint32 members,
        bytes32 summaryHash
    ) external onlyRole(PUBLISHER_ROLE) {
        if (cohortSummaryKey == bytes32(0) || valuationSnapshotKey == bytes32(0) || summaryHash == bytes32(0)) revert InvalidParams();
        if (_cohortSummaries[cohortSummaryKey].cohortSummaryKey != bytes32(0)) revert AlreadyPublished(cohortSummaryKey);
        _cohortSummaries[cohortSummaryKey] = CohortSummary({
            cohortSummaryKey: cohortSummaryKey,
            valuationSnapshotKey: valuationSnapshotKey,
            cohort: cohort,
            epvContributions: epvContributions,
            epvBenefits: epvBenefits,
            mwrBps: mwrBps,
            members: members,
            summaryHash: summaryHash,
            publisher: msg.sender
        });
        emit CohortSummaryPublished(cohortSummaryKey, cohort, summaryHash, msg.sender);
    }

    function publishResultBundle(
        bytes32 resultBundleKey,
        bytes32 parameterSetKey,
        bytes32 valuationSnapshotKey,
        bytes32 mortalityMethodKey,
        bytes32 epvMethodKey,
        bytes32 mwrMethodKey,
        bytes32 fairnessMethodKey,
        bytes32 schemeSummaryKey,
        bytes32 cohortDigest,
        bytes32 resultHash
    ) external onlyRole(PUBLISHER_ROLE) {
        if (
            resultBundleKey == bytes32(0) ||
            parameterSetKey == bytes32(0) ||
            valuationSnapshotKey == bytes32(0) ||
            mortalityMethodKey == bytes32(0) ||
            epvMethodKey == bytes32(0) ||
            mwrMethodKey == bytes32(0) ||
            fairnessMethodKey == bytes32(0) ||
            schemeSummaryKey == bytes32(0) ||
            cohortDigest == bytes32(0) ||
            resultHash == bytes32(0)
        ) revert InvalidParams();
        if (_resultBundles[resultBundleKey].resultBundleKey != bytes32(0)) revert AlreadyPublished(resultBundleKey);
        _resultBundles[resultBundleKey] = ResultBundle({
            resultBundleKey: resultBundleKey,
            parameterSetKey: parameterSetKey,
            valuationSnapshotKey: valuationSnapshotKey,
            mortalityMethodKey: mortalityMethodKey,
            epvMethodKey: epvMethodKey,
            mwrMethodKey: mwrMethodKey,
            fairnessMethodKey: fairnessMethodKey,
            schemeSummaryKey: schemeSummaryKey,
            cohortDigest: cohortDigest,
            resultHash: resultHash,
            publisher: msg.sender
        });
        emit ResultBundlePublished(resultBundleKey, valuationSnapshotKey, resultHash, msg.sender);
    }

    function getParameterSet(bytes32 parameterSetKey) external view returns (ParameterSet memory) {
        return _parameterSets[parameterSetKey];
    }

    function getValuationSnapshot(bytes32 valuationSnapshotKey) external view returns (ValuationSnapshot memory) {
        return _valuationSnapshots[valuationSnapshotKey];
    }

    function getSchemeSummary(bytes32 schemeSummaryKey) external view returns (SchemeSummary memory) {
        return _schemeSummaries[schemeSummaryKey];
    }

    function getCohortSummary(bytes32 cohortSummaryKey) external view returns (CohortSummary memory) {
        return _cohortSummaries[cohortSummaryKey];
    }

    function getResultBundle(bytes32 resultBundleKey) external view returns (ResultBundle memory) {
        return _resultBundles[resultBundleKey];
    }
}
