// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Test} from "forge-std/Test.sol";
import {MortalityOracle} from "../src/MortalityOracle.sol";

contract MortalityOracleTest is Test {
    MortalityOracle oracle;
    address owner = address(0xA11CE);
    address operator = address(0x0BA);
    address alice = address(0x1);

    bytes32 constant ORACLE = keccak256("ORACLE_ROLE");

    function setUp() public {
        vm.prank(owner);
        oracle = new MortalityOracle(owner);
        vm.prank(owner);
        oracle.grantRole(ORACLE, operator);
    }

    function testConfirmDeath() public {
        assertFalse(oracle.isDeceased(alice));
        vm.prank(operator);
        oracle.confirmDeath(alice, uint64(block.timestamp), keccak256("cert"));
        assertTrue(oracle.isDeceased(alice));
        assertEq(oracle.proof(alice), keccak256("cert"));
    }

    function testOnlyOperatorCanConfirm() public {
        vm.expectRevert();
        vm.prank(alice);
        oracle.confirmDeath(alice, 0, bytes32(0));
    }

    function testDoubleConfirmReverts() public {
        vm.prank(operator);
        oracle.confirmDeath(alice, 0, bytes32(0));
        vm.expectRevert(abi.encodeWithSelector(MortalityOracle.AlreadyDeceased.selector, alice));
        vm.prank(operator);
        oracle.confirmDeath(alice, 0, bytes32(0));
    }

    function testOwnerCanRevoke() public {
        vm.prank(operator);
        oracle.confirmDeath(alice, 0, bytes32(0));
        vm.prank(owner);
        oracle.revokeDeath(alice);
        assertFalse(oracle.isDeceased(alice));
    }

    function testFutureTimestampClampedToNow() public {
        uint64 far = uint64(block.timestamp + 1000);
        vm.prank(operator);
        oracle.confirmDeath(alice, far, bytes32(0));
        assertEq(oracle.deathTimestamp(alice), uint64(block.timestamp));
    }
}
