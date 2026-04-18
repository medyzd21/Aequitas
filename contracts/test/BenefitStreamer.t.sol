// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Test} from "forge-std/Test.sol";
import {BenefitStreamer} from "../src/BenefitStreamer.sol";
import {MortalityOracle} from "../src/MortalityOracle.sol";
import {IMortalityOracle} from "../src/interfaces/IMortalityOracle.sol";

contract BenefitStreamerTest is Test {
    BenefitStreamer streamer;
    MortalityOracle oracle;
    address owner = address(this);
    address admin = address(0xAD);
    address funder = address(0xF1);
    address alice = address(0xA11CE);

    bytes32 constant ORACLE = keccak256("ORACLE_ROLE");
    bytes32 constant STREAM = keccak256("STREAM_ADMIN_ROLE");
    bytes32 constant FUND   = keccak256("FUNDER_ROLE");

    function setUp() public {
        oracle = new MortalityOracle(owner);
        oracle.grantRole(ORACLE, owner);
        streamer = new BenefitStreamer(owner, IMortalityOracle(address(oracle)));
        streamer.grantRole(STREAM, admin);
        streamer.grantRole(FUND, funder);
        vm.deal(funder, 100 ether);
    }

    function testStartStreamAndClaim() public {
        vm.prank(admin);
        streamer.startStream(alice, uint128(12 ether) /* annual benefit */, 0);

        vm.prank(funder);
        streamer.fund{value: 10 ether}();

        // advance half a year → ~6 ETH accrued
        vm.warp(block.timestamp + 183 days);

        uint256 claimable = streamer.claimable(alice);
        assertApproxEqAbs(claimable, 6 ether, 0.05 ether);

        vm.prank(alice);
        uint256 amount = streamer.claim();
        assertApproxEqAbs(amount, 6 ether, 0.05 ether);
        assertEq(streamer.claimable(alice), 0);
    }

    function testStreamStopsAtDeath() public {
        vm.prank(admin);
        streamer.startStream(alice, uint128(12 ether), 0);
        vm.prank(funder);
        streamer.fund{value: 20 ether}();

        // half a year alive, then death
        vm.warp(block.timestamp + 183 days);
        oracle.confirmDeath(alice, uint64(block.timestamp), bytes32(0));

        vm.warp(block.timestamp + 365 days); // time passes after death
        vm.prank(alice);
        uint256 amount = streamer.claim();
        // should only cover up to death, not the extra year
        assertApproxEqAbs(amount, 6 ether, 0.05 ether);

        // subsequent claim reverts (no stream)
        vm.expectRevert(abi.encodeWithSelector(BenefitStreamer.NoStream.selector, alice));
        vm.prank(alice);
        streamer.claim();
    }

    function testInsufficientFundingReverts() public {
        vm.prank(admin);
        streamer.startStream(alice, uint128(365 ether), 0); // 1 eth/day
        // no funding
        vm.warp(block.timestamp + 2 days);
        vm.expectRevert();
        vm.prank(alice);
        streamer.claim();
    }
}
