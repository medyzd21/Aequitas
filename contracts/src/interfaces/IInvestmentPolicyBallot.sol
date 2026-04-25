// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

interface IInvestmentPolicyBallot {
    struct BallotView {
        uint256 id;
        string name;
        uint64 opensAt;
        uint64 closesAt;
        uint64 finalizedAt;
        bool finalized;
        bytes32 winnerPortfolioId;
        bytes32 adoptedAllocationHash;
        uint256 totalEligibleWeight;
        uint256 totalVotesWeight;
    }

    event BallotCreated(
        uint256 indexed ballotId,
        string name,
        uint64 opensAt,
        uint64 closesAt
    );

    event BallotPortfolioRegistered(
        uint256 indexed ballotId,
        bytes32 indexed portfolioId,
        bytes32 allocationHash
    );

    event BallotWeightsPublished(
        uint256 indexed ballotId,
        uint256 voterCount,
        uint256 totalEligibleWeight
    );

    event VoteCast(
        uint256 indexed ballotId,
        address indexed voter,
        bytes32 indexed portfolioId,
        uint256 weight
    );

    event BallotFinalized(
        uint256 indexed ballotId,
        bytes32 indexed winnerPortfolioId,
        bytes32 adoptedAllocationHash,
        uint256 winningWeight,
        uint64 finalizedAt
    );

    function ballotCount() external view returns (uint256);

    function getBallot(uint256 ballotId) external view returns (BallotView memory);

    function getPortfolioIds(uint256 ballotId) external view returns (bytes32[] memory);

    function getAllocationHash(uint256 ballotId, bytes32 portfolioId) external view returns (bytes32);

    function weightOf(uint256 ballotId, address voter) external view returns (uint256);

    function hasVoted(uint256 ballotId, address voter) external view returns (bool);

    function getTally(uint256 ballotId, bytes32 portfolioId) external view returns (uint256);
}
