// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @notice EPV values are passed as signed int256 scaled by 1e18 (i.e. a value
///         of 1e18 means an EPV of 1.0 in fixed-point). The corridor is a
///         pairwise check on ΔEPV_c = EPV_new_c − EPV_old_c, normalised by
///         the benchmark (the average of the baseline EPVs).
interface IFairnessGate {
    struct Proposal {
        string name;
        uint16[] cohorts;
        int256[] newEpvs;
        uint256 delta; // 1e18-scaled, e.g. 0.05e18 = 5%
        address proposer;
        uint64 submittedAt;
        bool accepted;
    }

    event BaselineSet(uint16[] cohorts, int256[] epvs);
    event ProposalSubmitted(uint256 indexed id, string name, address indexed proposer);
    event ProposalEvaluated(
        uint256 indexed id, bool passes, uint256 maxDeviation, uint16 worstA, uint16 worstB
    );
    event ProposalAccepted(uint256 indexed id);
    event ProposalRejected(uint256 indexed id);

    function setBaseline(uint16[] calldata cohorts, int256[] calldata epvs) external;
    function submitAndEvaluate(
        string calldata name,
        uint16[] calldata cohorts,
        int256[] calldata newEpvs,
        uint256 delta
    ) external returns (uint256 id, bool passes);

    function baselineEpv(uint16 cohort) external view returns (int256);
    function proposalCount() external view returns (uint256);
    function getProposal(uint256 id) external view returns (Proposal memory);
}
