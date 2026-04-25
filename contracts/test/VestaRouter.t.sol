// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Test} from "forge-std/Test.sol";
import {CohortLedger} from "../src/CohortLedger.sol";
import {LongevaPool} from "../src/LongevaPool.sol";
import {MortalityOracle} from "../src/MortalityOracle.sol";
import {BenefitStreamer} from "../src/BenefitStreamer.sol";
import {VestaRouter} from "../src/VestaRouter.sol";
import {ICohortLedger} from "../src/interfaces/ICohortLedger.sol";
import {ILongevaPool} from "../src/interfaces/ILongevaPool.sol";
import {IMortalityOracle} from "../src/interfaces/IMortalityOracle.sol";

contract VestaRouterTest is Test {
    CohortLedger ledger;
    LongevaPool pool;
    MortalityOracle oracle;
    BenefitStreamer streamer;
    VestaRouter router;

    address owner = address(this);
    address depositor = address(0xDE);
    address operator  = address(0x0B);
    address alice = address(0xA11CE);

    function setUp() public {
        oracle = new MortalityOracle(owner);
        ledger = new CohortLedger(owner, 1e18);
        pool    = new LongevaPool(owner, IMortalityOracle(address(oracle)));
        streamer = new BenefitStreamer(owner, IMortalityOracle(address(oracle)));
        router   = new VestaRouter(
            owner,
            ICohortLedger(address(ledger)),
            ILongevaPool(address(pool)),
            streamer
        );

        // Roles --------------------------------------------------------------
        ledger.grantRole(keccak256("REGISTRAR_ROLE"), owner);
        ledger.grantRole(keccak256("CONTRIBUTION_ROLE"), owner);
        ledger.grantRole(keccak256("RETIREMENT_ROLE"), owner);
        ledger.grantRole(keccak256("RETIREMENT_ROLE"), address(router));

        pool.grantRole(keccak256("DEPOSIT_ROLE"), depositor);
        pool.grantRole(keccak256("PAYOUT_ROLE"), address(router));

        streamer.grantRole(keccak256("STREAM_ADMIN_ROLE"), address(router));
        streamer.grantRole(keccak256("FUNDER_ROLE"), address(router));

        router.grantRole(keccak256("OPERATOR_ROLE"), operator);

        // Seed ---------------------------------------------------------------
        ledger.registerMember(alice, 1960);
        ledger.contribute(alice, 5 ether);

        vm.deal(depositor, 50 ether);
        vm.prank(depositor);
        pool.deposit{value: 30 ether}(alice, 30 ether);
    }

    function testOpenRetirementStartsStream() public {
        vm.prank(operator);
        router.openRetirement(alice, 10 ether, uint128(12 ether) /* yr */, 0);

        ICohortLedger.Member memory m = ledger.getMember(alice);
        assertEq(m.piuBalance, 0);
        assertFalse(m.active);
        assertTrue(m.retired);
        assertEq(pool.totalAssets(), 20 ether);
        assertEq(streamer.fundedBalance(), 10 ether);

        vm.warp(block.timestamp + 183 days);
        uint256 claimable = streamer.claimable(alice);
        assertApproxEqAbs(claimable, 6 ether, 0.05 ether);
    }

    function testCannotOpenIfUnregistered() public {
        address bob = address(0xB0B);

        vm.expectRevert(abi.encodeWithSelector(VestaRouter.MemberNotRetired.selector, bob));
        vm.prank(operator);
        router.openRetirement(bob, 1 ether, uint128(1 ether), 0);
    }
}
