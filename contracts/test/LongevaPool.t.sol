// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Test} from "forge-std/Test.sol";
import {LongevaPool} from "../src/LongevaPool.sol";
import {MortalityOracle} from "../src/MortalityOracle.sol";
import {IMortalityOracle} from "../src/interfaces/IMortalityOracle.sol";

contract LongevaPoolTest is Test {
    LongevaPool pool;
    MortalityOracle oracle;
    address owner = address(this);
    address depositor = address(0xDEAD_BEEF);
    address router = address(0xFACE);
    address yielder = address(0xFADE);
    address alice = address(0xA11CE);
    address bob = address(0xB0B);

    bytes32 constant ORACLE = keccak256("ORACLE_ROLE");
    bytes32 constant DEP = keccak256("DEPOSIT_ROLE");
    bytes32 constant PAY = keccak256("PAYOUT_ROLE");
    bytes32 constant YLD = keccak256("YIELD_ROLE");

    function setUp() public {
        oracle = new MortalityOracle(owner);
        oracle.grantRole(ORACLE, owner);

        pool = new LongevaPool(owner, IMortalityOracle(address(oracle)));
        pool.grantRole(DEP, depositor);
        pool.grantRole(PAY, router);
        pool.grantRole(YLD, yielder);

        vm.deal(depositor, 100 ether);
        vm.deal(yielder, 100 ether);
    }

    function testFirstDepositIsOneToOne() public {
        vm.prank(depositor);
        pool.deposit{value: 5 ether}(alice, 5 ether);
        assertEq(pool.sharesOf(alice), 5 ether);
        assertEq(pool.totalAssets(), 5 ether);
        assertEq(pool.totalShares(), 5 ether);
    }

    function testYieldRaisesNavPerShare() public {
        vm.prank(depositor);
        pool.deposit{value: 10 ether}(alice, 10 ether);

        // +10% yield
        vm.prank(yielder);
        pool.simulateYield{value: 1 ether}();
        assertEq(pool.totalAssets(), 11 ether);
        assertEq(pool.shareToAssets(10 ether), 11 ether);
    }

    function testMortalityCreditBenefitsSurvivors() public {
        vm.startPrank(depositor);
        pool.deposit{value: 5 ether}(alice, 5 ether);
        pool.deposit{value: 5 ether}(bob, 5 ether);
        vm.stopPrank();
        // 10 eth assets, 10 shares. Each holds 5 shares.

        oracle.confirmDeath(alice, 0, bytes32(0));
        pool.releaseMortalityCredit(alice);

        // totalAssets unchanged, totalShares -= 5 → Bob's 5 shares now back 10 ETH
        assertEq(pool.totalAssets(), 10 ether);
        assertEq(pool.totalShares(), 5 ether);
        assertEq(pool.shareToAssets(pool.sharesOf(bob)), 10 ether);
    }

    function testPayToOnlyByPayoutRole() public {
        vm.prank(depositor);
        pool.deposit{value: 3 ether}(alice, 3 ether);

        vm.expectRevert();
        pool.payTo(alice, 1 ether);

        vm.prank(router);
        pool.payTo(alice, 1 ether);
        assertEq(pool.totalAssets(), 2 ether);
    }

    function testCannotReleaseIfAlive() public {
        vm.prank(depositor);
        pool.deposit{value: 1 ether}(alice, 1 ether);
        vm.expectRevert(abi.encodeWithSelector(LongevaPool.NotDeceased.selector, alice));
        pool.releaseMortalityCredit(alice);
    }
}
