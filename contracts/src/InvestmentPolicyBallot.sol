// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {IInvestmentPolicyBallot} from "./interfaces/IInvestmentPolicyBallot.sol";
import {Owned} from "./utils/Owned.sol";
import {Roles} from "./utils/Roles.sol";

/**
 * @title InvestmentPolicyBallot
 * @notice Publishes member-governed investment-policy outcomes on chain.
 *
 * The chain is only used for the execution and audit trail:
 *
 * - create a named ballot round,
 * - publish the predefined model-portfolio ids plus allocation hashes,
 * - publish the off-chain voting-weight snapshot,
 * - collect one vote per eligible member,
 * - finalize and publish the winning policy hash.
 *
 * The chain does not fit portfolio models, compute contribution windows,
 * or trade assets. Those remain off-chain in Python.
 */
contract InvestmentPolicyBallot is IInvestmentPolicyBallot, Roles {
    bytes32 public constant BALLOT_ADMIN_ROLE = keccak256("BALLOT_ADMIN_ROLE");
    bytes32 public constant SNAPSHOT_ROLE = keccak256("SNAPSHOT_ROLE");

    struct Ballot {
        string name;
        uint64 opensAt;
        uint64 closesAt;
        uint64 finalizedAt;
        bool finalized;
        bytes32 winnerPortfolioId;
        bytes32 adoptedAllocationHash;
        uint256 totalEligibleWeight;
        uint256 totalVotesWeight;
        bytes32[] portfolioIds;
    }

    Ballot[] private _ballots;
    mapping(uint256 => mapping(bytes32 => bytes32)) private _allocationHashOf;
    mapping(uint256 => mapping(bytes32 => bool)) private _portfolioExists;
    mapping(uint256 => mapping(address => uint256)) private _weightOf;
    mapping(uint256 => mapping(address => bool)) private _hasVoted;
    mapping(uint256 => mapping(bytes32 => uint256)) private _tallyOf;

    error InvalidBallotWindow();
    error LengthMismatch();
    error EmptyPortfolioSet();
    error UnknownPortfolio(bytes32 portfolioId);
    error BallotNotOpen(uint256 ballotId, uint64 opensAt, uint64 closesAt, uint64 timestamp);
    error BallotNotClosed(uint256 ballotId, uint64 closesAt, uint64 timestamp);
    error BallotAlreadyFinalized(uint256 ballotId);
    error DuplicateWeightSnapshot(address voter);
    error DuplicatePortfolio(bytes32 portfolioId);
    error IneligibleVoter(address voter);
    error AlreadyVoted(uint256 ballotId, address voter);

    constructor(address initialOwner) Owned(initialOwner) {}

    function createBallot(
        string calldata name,
        bytes32[] calldata portfolioIds,
        bytes32[] calldata allocationHashes,
        uint64 opensAt,
        uint64 closesAt
    ) external onlyRole(BALLOT_ADMIN_ROLE) {
        if (portfolioIds.length == 0) revert EmptyPortfolioSet();
        if (portfolioIds.length != allocationHashes.length) revert LengthMismatch();
        if (opensAt >= closesAt) revert InvalidBallotWindow();

        uint256 ballotId = _ballots.length;
        _ballots.push();
        Ballot storage ballot = _ballots[ballotId];
        ballot.name = name;
        ballot.opensAt = opensAt;
        ballot.closesAt = closesAt;

        for (uint256 i = 0; i < portfolioIds.length; i++) {
            bytes32 portfolioId = portfolioIds[i];
            if (_portfolioExists[ballotId][portfolioId]) revert DuplicatePortfolio(portfolioId);
            ballot.portfolioIds.push(portfolioId);
            _portfolioExists[ballotId][portfolioId] = true;
            _allocationHashOf[ballotId][portfolioId] = allocationHashes[i];
            emit BallotPortfolioRegistered(ballotId, portfolioId, allocationHashes[i]);
        }

        emit BallotCreated(ballotId, name, opensAt, closesAt);
    }

    function setBallotWeights(
        uint256 ballotId,
        address[] calldata voters,
        uint256[] calldata weights
    ) external onlyRole(SNAPSHOT_ROLE) {
        if (voters.length != weights.length) revert LengthMismatch();
        Ballot storage ballot = _requireBallot(ballotId);
        if (ballot.finalized) revert BallotAlreadyFinalized(ballotId);
        if (block.timestamp > ballot.opensAt) {
            revert BallotNotOpen(ballotId, ballot.opensAt, ballot.closesAt, uint64(block.timestamp));
        }

        uint256 addedWeight = 0;
        for (uint256 i = 0; i < voters.length; i++) {
            address voter = voters[i];
            uint256 weight = weights[i];
            if (_weightOf[ballotId][voter] != 0) revert DuplicateWeightSnapshot(voter);
            if (weight == 0) revert IneligibleVoter(voter);
            _weightOf[ballotId][voter] = weight;
            addedWeight += weight;
        }
        ballot.totalEligibleWeight += addedWeight;
        emit BallotWeightsPublished(ballotId, voters.length, ballot.totalEligibleWeight);
    }

    function castVote(uint256 ballotId, bytes32 portfolioId) external {
        Ballot storage ballot = _requireBallot(ballotId);
        if (ballot.finalized) revert BallotAlreadyFinalized(ballotId);
        if (block.timestamp < ballot.opensAt || block.timestamp > ballot.closesAt) {
            revert BallotNotOpen(ballotId, ballot.opensAt, ballot.closesAt, uint64(block.timestamp));
        }
        if (!_portfolioExists[ballotId][portfolioId]) revert UnknownPortfolio(portfolioId);
        if (_hasVoted[ballotId][msg.sender]) revert AlreadyVoted(ballotId, msg.sender);

        uint256 weight = _weightOf[ballotId][msg.sender];
        if (weight == 0) revert IneligibleVoter(msg.sender);

        _hasVoted[ballotId][msg.sender] = true;
        _tallyOf[ballotId][portfolioId] += weight;
        ballot.totalVotesWeight += weight;

        emit VoteCast(ballotId, msg.sender, portfolioId, weight);
    }

    function finalizeBallot(uint256 ballotId) external onlyRole(BALLOT_ADMIN_ROLE) {
        Ballot storage ballot = _requireBallot(ballotId);
        if (ballot.finalized) revert BallotAlreadyFinalized(ballotId);
        if (block.timestamp < ballot.closesAt) {
            revert BallotNotClosed(ballotId, ballot.closesAt, uint64(block.timestamp));
        }

        bytes32 winnerPortfolioId = ballot.portfolioIds[0];
        uint256 winningWeight = _tallyOf[ballotId][winnerPortfolioId];
        for (uint256 i = 1; i < ballot.portfolioIds.length; i++) {
            bytes32 candidate = ballot.portfolioIds[i];
            uint256 candidateWeight = _tallyOf[ballotId][candidate];
            if (candidateWeight > winningWeight) {
                winnerPortfolioId = candidate;
                winningWeight = candidateWeight;
            }
        }

        ballot.finalized = true;
        ballot.finalizedAt = uint64(block.timestamp);
        ballot.winnerPortfolioId = winnerPortfolioId;
        ballot.adoptedAllocationHash = _allocationHashOf[ballotId][winnerPortfolioId];

        emit BallotFinalized(
            ballotId,
            winnerPortfolioId,
            ballot.adoptedAllocationHash,
            winningWeight,
            ballot.finalizedAt
        );
    }

    function ballotCount() external view returns (uint256) {
        return _ballots.length;
    }

    function getBallot(uint256 ballotId) external view returns (BallotView memory) {
        Ballot storage ballot = _ballots[ballotId];
        return BallotView({
            id: ballotId,
            name: ballot.name,
            opensAt: ballot.opensAt,
            closesAt: ballot.closesAt,
            finalizedAt: ballot.finalizedAt,
            finalized: ballot.finalized,
            winnerPortfolioId: ballot.winnerPortfolioId,
            adoptedAllocationHash: ballot.adoptedAllocationHash,
            totalEligibleWeight: ballot.totalEligibleWeight,
            totalVotesWeight: ballot.totalVotesWeight
        });
    }

    function getPortfolioIds(uint256 ballotId) external view returns (bytes32[] memory) {
        return _ballots[ballotId].portfolioIds;
    }

    function getAllocationHash(uint256 ballotId, bytes32 portfolioId) external view returns (bytes32) {
        return _allocationHashOf[ballotId][portfolioId];
    }

    function weightOf(uint256 ballotId, address voter) external view returns (uint256) {
        return _weightOf[ballotId][voter];
    }

    function hasVoted(uint256 ballotId, address voter) external view returns (bool) {
        return _hasVoted[ballotId][voter];
    }

    function getTally(uint256 ballotId, bytes32 portfolioId) external view returns (uint256) {
        return _tallyOf[ballotId][portfolioId];
    }

    function _requireBallot(uint256 ballotId) internal view returns (Ballot storage ballot) {
        ballot = _ballots[ballotId];
    }
}
