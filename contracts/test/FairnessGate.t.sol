// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Test} from "forge-std/Test.sol";
import {FairnessGate} from "../src/FairnessGate.sol";
import {IFairnessGate} from "../src/interfaces/IFairnessGate.sol";

contract FairnessGateTest is Test {
    FairnessGate gate;
    address owner = address(0xA);
    address baselineAdmin = address(0xB);
    address proposer = address(0xC);

    bytes32 constant BASE = keccak256("BASELINE_ROLE");
    bytes32 constant PROP = keccak256("PROPOSER_ROLE");

    function setUp() public {
        vm.prank(owner);
        gate = new FairnessGate(owner);
        vm.startPrank(owner);
        gate.grantRole(BASE, baselineAdmin);
        gate.grantRole(PROP, proposer);
        vm.stopPrank();

        // Baseline: 3 cohorts, all EPV = 100e18.
        uint16[] memory cohorts = new uint16[](3);
        cohorts[0] = 1960;
        cohorts[1] = 1970;
        cohorts[2] = 1980;
        int256[] memory epvs = new int256[](3);
        epvs[0] = 100e18;
        epvs[1] = 100e18;
        epvs[2] = 100e18;
        vm.prank(baselineAdmin);
        gate.setBaseline(cohorts, epvs);
    }

    function _cohorts() internal pure returns (uint16[] memory c) {
        c = new uint16[](3);
        c[0] = 1960; c[1] = 1970; c[2] = 1980;
    }

    function testBalancedProposalPasses() public {
        // all +2% → zero pairwise dispersion
        int256[] memory n = new int256[](3);
        n[0] = 102e18; n[1] = 102e18; n[2] = 102e18;
        vm.prank(proposer);
        (, bool passes) = gate.submitAndEvaluate("balanced", _cohorts(), n, 0.05e18);
        assertTrue(passes);
    }

    function testSkewedProposalFails() public {
        // +10% / 0% / −10% → big pairwise dispersion
        int256[] memory n = new int256[](3);
        n[0] = 110e18; n[1] = 100e18; n[2] = 90e18;
        vm.prank(proposer);
        (, bool passes) = gate.submitAndEvaluate("skewed", _cohorts(), n, 0.05e18);
        assertFalse(passes);
    }

    function testAcceptedProposalUpdatesBaseline() public {
        int256[] memory n = new int256[](3);
        n[0] = 101e18; n[1] = 101e18; n[2] = 101e18;
        vm.prank(proposer);
        gate.submitAndEvaluate("tiny", _cohorts(), n, 0.05e18);
        assertEq(gate.baselineEpv(1960), 101e18);
        assertEq(gate.baselineEpv(1970), 101e18);
        assertEq(gate.baselineEpv(1980), 101e18);
    }

    function testRejectedProposalDoesNotUpdateBaseline() public {
        int256[] memory n = new int256[](3);
        n[0] = 130e18; n[1] = 100e18; n[2] = 70e18;
        vm.prank(proposer);
        gate.submitAndEvaluate("skewed", _cohorts(), n, 0.05e18);
        assertEq(gate.baselineEpv(1960), 100e18);
    }

    function testProposalCountIncrements() public {
        int256[] memory n = new int256[](3);
        n[0] = 101e18; n[1] = 101e18; n[2] = 101e18;
        vm.prank(proposer);
        gate.submitAndEvaluate("a", _cohorts(), n, 0.05e18);
        vm.prank(proposer);
        gate.submitAndEvaluate("b", _cohorts(), n, 0.05e18);
        assertEq(gate.proposalCount(), 2);
    }

    function testOnlyProposerCanSubmit() public {
        int256[] memory n = new int256[](3);
        n[0] = 101e18; n[1] = 101e18; n[2] = 101e18;
        vm.expectRevert();
        vm.prank(address(0x999));
        gate.submitAndEvaluate("x", _cohorts(), n, 0.05e18);
    }
}
