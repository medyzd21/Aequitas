// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Test} from "forge-std/Test.sol";
import {StressOracle} from "../src/StressOracle.sol";

contract StressOracleTest is Test {
    StressOracle oracle;
    address owner = address(this);
    address reporter = address(0xBEEF);

    function setUp() public {
        oracle = new StressOracle(owner);
        oracle.grantRole(keccak256("REPORTER_ROLE"), reporter);
    }

    function testUpdateStress() public {
        vm.prank(reporter);
        oracle.updateStressLevel(0.42e18, bytes32("p95_gini"), keccak256("runX"));
        assertEq(oracle.stressLevel(), 0.42e18);
        assertEq(oracle.lastReason(), bytes32("p95_gini"));
    }

    function testOutOfRangeReverts() public {
        vm.expectRevert(abi.encodeWithSelector(StressOracle.LevelOutOfRange.selector, uint256(2e18)));
        vm.prank(reporter);
        oracle.updateStressLevel(2e18, 0, 0);
    }

    function testOnlyReporter() public {
        vm.expectRevert();
        oracle.updateStressLevel(0, 0, 0);
    }
}
