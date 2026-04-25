// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Test} from "forge-std/Test.sol";
import {InvestmentPolicyBallot} from "../src/InvestmentPolicyBallot.sol";
import {IInvestmentPolicyBallot} from "../src/interfaces/IInvestmentPolicyBallot.sol";

contract InvestmentPolicyBallotTest is Test {
    InvestmentPolicyBallot ballot;

    address owner = address(0xA11CE);
    address snapshotter = address(0xBEEF);
    address voterA = address(0x1001);
    address voterB = address(0x1002);
    address voterC = address(0x1003);

    bytes32 constant BALLOT_ADMIN_ROLE = keccak256("BALLOT_ADMIN_ROLE");
    bytes32 constant SNAPSHOT_ROLE = keccak256("SNAPSHOT_ROLE");

    bytes32[] portfolioIds;
    bytes32[] allocationHashes;

    function setUp() public {
        vm.prank(owner);
        ballot = new InvestmentPolicyBallot(owner);

        vm.startPrank(owner);
        ballot.grantRole(BALLOT_ADMIN_ROLE, owner);
        ballot.grantRole(SNAPSHOT_ROLE, snapshotter);
        vm.stopPrank();

        portfolioIds.push(bytes32("growth"));
        portfolioIds.push(bytes32("balanced"));
        portfolioIds.push(bytes32("defensive"));

        allocationHashes.push(keccak256("growth"));
        allocationHashes.push(keccak256("balanced"));
        allocationHashes.push(keccak256("defensive"));
    }

    function _createDefaultBallot() internal {
        vm.prank(owner);
        ballot.createBallot("2026 allocation round", portfolioIds, allocationHashes, 100, 200);
    }

    function _publishWeights() internal {
        address[] memory voters = new address[](3);
        uint256[] memory weights = new uint256[](3);
        voters[0] = voterA;
        voters[1] = voterB;
        voters[2] = voterC;
        weights[0] = 50_000;
        weights[1] = 35_000;
        weights[2] = 15_000;

        vm.prank(snapshotter);
        ballot.setBallotWeights(0, voters, weights);
    }

    function testCreateBallotStoresPortfolioSet() public {
        _createDefaultBallot();

        assertEq(ballot.ballotCount(), 1);
        IInvestmentPolicyBallot.BallotView memory view_ = ballot.getBallot(0);
        assertEq(view_.opensAt, 100);
        assertEq(view_.closesAt, 200);

        bytes32[] memory ids = ballot.getPortfolioIds(0);
        assertEq(ids.length, 3);
        assertEq(ids[0], portfolioIds[0]);
        assertEq(ballot.getAllocationHash(0, ids[1]), allocationHashes[1]);
    }

    function testSetWeightsStoresSnapshot() public {
        _createDefaultBallot();
        _publishWeights();

        assertEq(ballot.weightOf(0, voterA), 50_000);
        assertEq(ballot.weightOf(0, voterB), 35_000);
        IInvestmentPolicyBallot.BallotView memory view_ = ballot.getBallot(0);
        assertEq(view_.totalEligibleWeight, 100_000);
    }

    function testCastVoteTalliesWeight() public {
        _createDefaultBallot();
        _publishWeights();

        vm.warp(120);
        vm.prank(voterA);
        ballot.castVote(0, portfolioIds[1]);

        assertEq(ballot.getTally(0, portfolioIds[1]), 50_000);
        assertTrue(ballot.hasVoted(0, voterA));
    }

    function testPreventDoubleVote() public {
        _createDefaultBallot();
        _publishWeights();

        vm.warp(120);
        vm.startPrank(voterA);
        ballot.castVote(0, portfolioIds[0]);
        vm.expectRevert(abi.encodeWithSelector(InvestmentPolicyBallot.AlreadyVoted.selector, 0, voterA));
        ballot.castVote(0, portfolioIds[1]);
        vm.stopPrank();
    }

    function testRejectOutOfWindowVote() public {
        _createDefaultBallot();
        _publishWeights();

        vm.warp(99);
        vm.prank(voterA);
        vm.expectRevert();
        ballot.castVote(0, portfolioIds[0]);

        vm.warp(201);
        vm.prank(voterA);
        vm.expectRevert();
        ballot.castVote(0, portfolioIds[0]);
    }

    function testFinalizeSelectsWinner() public {
        _createDefaultBallot();
        _publishWeights();

        vm.warp(120);
        vm.prank(voterA);
        ballot.castVote(0, portfolioIds[1]);
        vm.prank(voterB);
        ballot.castVote(0, portfolioIds[1]);
        vm.prank(voterC);
        ballot.castVote(0, portfolioIds[2]);

        vm.warp(210);
        vm.prank(owner);
        ballot.finalizeBallot(0);

        IInvestmentPolicyBallot.BallotView memory view_ = ballot.getBallot(0);
        assertTrue(view_.finalized);
        assertEq(view_.winnerPortfolioId, portfolioIds[1]);
        assertEq(view_.adoptedAllocationHash, allocationHashes[1]);
        assertEq(view_.totalVotesWeight, 100_000);
    }

    function testTieBreakUsesDeclaredPortfolioOrder() public {
        _createDefaultBallot();
        _publishWeights();

        vm.warp(120);
        vm.prank(voterA);
        ballot.castVote(0, portfolioIds[0]);
        vm.prank(voterB);
        ballot.castVote(0, portfolioIds[1]);
        vm.prank(voterC);
        ballot.castVote(0, portfolioIds[1]);

        vm.warp(210);
        vm.prank(owner);
        ballot.finalizeBallot(0);

        IInvestmentPolicyBallot.BallotView memory view_ = ballot.getBallot(0);
        assertEq(view_.winnerPortfolioId, portfolioIds[0]);
    }
}
