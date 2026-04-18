// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Test} from "forge-std/Test.sol";
import {StressOracle} from "../src/StressOracle.sol";
import {BackstopVault} from "../src/BackstopVault.sol";
import {IStressOracle} from "../src/interfaces/IStressOracle.sol";

contract BackstopVaultTest is Test {
    StressOracle stress;
    BackstopVault vault;

    address owner = address(this);
    address reporter = address(0xBEEF);
    address guardian = address(0xGA);
    address depositor = address(0xDE);
    address beneficiary = address(0xB1);

    function setUp() public {
        stress = new StressOracle(owner);
        stress.grantRole(keccak256("REPORTER_ROLE"), reporter);

        vault = new BackstopVault(
            owner,
            IStressOracle(address(stress)),
            beneficiary,
            0.70e18,      // release threshold 0.7
            5000          // cap 50% per call
        );
        vault.grantRole(keccak256("GUARDIAN_ROLE"), guardian);
        vault.grantRole(keccak256("DEPOSITOR_ROLE"), depositor);

        vm.deal(depositor, 100 ether);
    }

    function testDepositAndReserve() public {
        vm.prank(depositor);
        vault.deposit{value: 10 ether}();
        assertEq(vault.reserve(), 10 ether);
        assertEq(vault.totalDeposited(), 10 ether);
    }

    function testReleaseRequiresStress() public {
        vm.prank(depositor);
        vault.deposit{value: 10 ether}();
        vm.expectRevert();
        vm.prank(guardian);
        vault.release(1 ether);
    }

    function testReleaseWhenStressed() public {
        vm.prank(depositor);
        vault.deposit{value: 10 ether}();

        vm.prank(reporter);
        stress.updateStressLevel(0.80e18, bytes32("p95_gini>threshold"), bytes32(0));

        uint256 beforeBal = beneficiary.balance;
        vm.prank(guardian);
        vault.release(4 ether);
        assertEq(beneficiary.balance - beforeBal, 4 ether);
        assertEq(vault.totalReleased(), 4 ether);
    }

    function testCapExceededReverts() public {
        vm.prank(depositor);
        vault.deposit{value: 10 ether}();
        vm.prank(reporter);
        stress.updateStressLevel(0.80e18, 0, 0);
        vm.expectRevert();
        vm.prank(guardian);
        vault.release(6 ether); // > 50% of 10
    }
}
