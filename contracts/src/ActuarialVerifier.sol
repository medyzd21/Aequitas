// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {IActuarialVerifier} from "./interfaces/IActuarialVerifier.sol";

/**
 * @title ActuarialVerifier
 * @notice Small deterministic actuarial verification kernel.
 *
 * This contract does not attempt to reproduce the full pension engine.
 * It only verifies bounded spot checks that are simple enough to audit:
 *
 * - Money-worth-ratio checks from published EPV summaries,
 * - pairwise fairness-corridor checks from cohort EPV vectors,
 * - a single-member EPV over a short declared cashflow vector.
 *
 * Everything else — simulation, mortality fitting, member-level valuation
 * loops, and stochastic stress — stays off-chain in Python.
 */
contract ActuarialVerifier is IActuarialVerifier {
    uint256 internal constant SCALE = 1e18;
    uint256 internal constant MAX_VECTOR_LENGTH = 64;

    error InvalidParams();
    error VectorTooLong(uint256 length, uint256 maxLength);
    error LengthMismatch();

    function verifyMWR(
        uint256 epvBenefits,
        uint256 epvContributions,
        uint256 expectedMwr,
        uint256 toleranceBps
    ) external pure returns (bool passes, uint256 computedMwr, uint256 deviationBps) {
        if (epvContributions == 0) revert InvalidParams();
        computedMwr = (epvBenefits * SCALE) / epvContributions;
        deviationBps = _deviationBps(computedMwr, expectedMwr);
        passes = deviationBps <= toleranceBps;
    }

    function verifyCorridorPass(
        int256[] calldata cohortEpvsBefore,
        int256[] calldata cohortEpvsAfter,
        uint256 epvBenchmark,
        uint256 deltaBps
    ) external pure returns (bool passes, uint256 maxDeviationBps) {
        uint256 n = cohortEpvsBefore.length;
        if (n == 0 || epvBenchmark == 0) revert InvalidParams();
        if (n != cohortEpvsAfter.length) revert LengthMismatch();
        if (n > MAX_VECTOR_LENGTH) revert VectorTooLong(n, MAX_VECTOR_LENGTH);

        for (uint256 i = 0; i < n; i++) {
            int256 deltaI = cohortEpvsAfter[i] - cohortEpvsBefore[i];
            for (uint256 j = 0; j < n; j++) {
                int256 deltaJ = cohortEpvsAfter[j] - cohortEpvsBefore[j];
                uint256 deviation = (uint256(_abs(deltaI - deltaJ)) * 10_000) / epvBenchmark;
                if (deviation > maxDeviationBps) {
                    maxDeviationBps = deviation;
                }
            }
        }
        passes = maxDeviationBps <= deltaBps;
    }

    function verifySingleMemberEPV(
        int256[] calldata cashflows,
        uint256[] calldata discountFactors,
        uint256[] calldata survivalProbabilities,
        int256 expectedEpv,
        uint256 toleranceBps
    ) external pure returns (bool passes, int256 computedEpv, uint256 deviationBps) {
        uint256 n = cashflows.length;
        if (n == 0) revert InvalidParams();
        if (n != discountFactors.length || n != survivalProbabilities.length) revert LengthMismatch();
        if (n > MAX_VECTOR_LENGTH) revert VectorTooLong(n, MAX_VECTOR_LENGTH);

        for (uint256 i = 0; i < n; i++) {
            int256 discounted = (cashflows[i] * int256(discountFactors[i])) / int256(SCALE);
            int256 weighted = (discounted * int256(survivalProbabilities[i])) / int256(SCALE);
            computedEpv += weighted;
        }

        deviationBps = _deviationBpsSigned(computedEpv, expectedEpv);
        passes = deviationBps <= toleranceBps;
    }

    function _deviationBps(uint256 computed, uint256 expected) internal pure returns (uint256) {
        if (expected == 0) {
            return computed == 0 ? 0 : type(uint256).max;
        }
        uint256 diff = computed > expected ? computed - expected : expected - computed;
        return (diff * 10_000) / expected;
    }

    function _deviationBpsSigned(int256 computed, int256 expected) internal pure returns (uint256) {
        uint256 expectedAbs = uint256(_abs(expected));
        if (expectedAbs == 0) {
            return computed == 0 ? 0 : type(uint256).max;
        }
        return (uint256(_abs(computed - expected)) * 10_000) / expectedAbs;
    }

    function _abs(int256 x) internal pure returns (int256) {
        return x >= 0 ? x : -x;
    }
}
