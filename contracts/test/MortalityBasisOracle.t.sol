// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Test} from "forge-std/Test.sol";
import {MortalityBasisOracle} from "../src/MortalityBasisOracle.sol";
import {IMortalityBasisOracle} from "../src/interfaces/IMortalityBasisOracle.sol";

contract MortalityBasisOracleTest is Test {
    MortalityBasisOracle oracle;
    address owner = address(0xA11CE);
    address publisher = address(0xBEEF);

    bytes32 constant PUBLISHER_ROLE = keccak256("PUBLISHER_ROLE");

    function setUp() public {
        vm.prank(owner);
        oracle = new MortalityBasisOracle(owner);
        vm.prank(owner);
        oracle.grantRole(PUBLISHER_ROLE, publisher);
    }

    function testPublishBasisStoresSnapshot() public {
        vm.prank(publisher);
        oracle.publishBasis(
            1,
            keccak256("gompertz_makeham_v1"),
            keccak256("digest"),
            2500,
            1_777_000_000,
            keccak256("study"),
            2_500_000,
            34,
            301_000,
            true
        );

        assertEq(oracle.latestVersion(), 1);
        IMortalityBasisOracle.BasisSnapshot memory snap = oracle.currentBasis();
        assertEq(snap.version, 1);
        assertEq(snap.credibilityBps, 2500);
        assertEq(snap.observedDeaths, 34);
        assertEq(snap.publisher, publisher);
        assertTrue(snap.advisory);
    }

    function testOnlyPublisherCanPublish() public {
        vm.expectRevert();
        oracle.publishBasis(1, bytes32(0), bytes32(0), 0, 0, bytes32(0), 0, 0, 0, true);
    }

    function testRejectsDuplicateVersion() public {
        vm.startPrank(publisher);
        oracle.publishBasis(1, bytes32(0), bytes32(0), 0, 0, bytes32(0), 0, 0, 0, true);
        vm.expectRevert(abi.encodeWithSelector(MortalityBasisOracle.VersionAlreadyExists.selector, uint64(1)));
        oracle.publishBasis(1, bytes32(0), bytes32(0), 0, 0, bytes32(0), 0, 0, 0, true);
        vm.stopPrank();
    }

    function testRejectsOutOfOrderVersion() public {
        vm.startPrank(publisher);
        oracle.publishBasis(2, bytes32(0), bytes32(0), 0, 0, bytes32(0), 0, 0, 0, true);
        vm.expectRevert(abi.encodeWithSelector(MortalityBasisOracle.VersionOutOfOrder.selector, uint64(2), uint64(1)));
        oracle.publishBasis(1, bytes32(0), bytes32(0), 0, 0, bytes32(0), 0, 0, 0, true);
        vm.stopPrank();
    }
}
