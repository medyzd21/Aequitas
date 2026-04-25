// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

interface IActuarialVerifier {
    function verifyMWR(
        uint256 epvBenefits,
        uint256 epvContributions,
        uint256 expectedMwr,
        uint256 toleranceBps
    ) external pure returns (bool passes, uint256 computedMwr, uint256 deviationBps);

    function verifyCorridorPass(
        int256[] calldata cohortEpvsBefore,
        int256[] calldata cohortEpvsAfter,
        uint256 epvBenchmark,
        uint256 deltaBps
    ) external pure returns (bool passes, uint256 maxDeviationBps);

    function verifySingleMemberEPV(
        int256[] calldata cashflows,
        uint256[] calldata discountFactors,
        uint256[] calldata survivalProbabilities,
        int256 expectedEpv,
        uint256 toleranceBps
    ) external pure returns (bool passes, int256 computedEpv, uint256 deviationBps);
}
