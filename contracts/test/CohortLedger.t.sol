// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Test, console2} from "forge-std/Test.sol";
import {CohortLedger} from "../src/CohortLedger.sol";
import {ICohortLedger} from "../src/interfaces/ICohortLedger.sol";

contract CohortLedgerTest is Test {
    CohortLedger ledger;
    address owner = address(0xA11CE);
    address registrar = address(0xBEEF);
    address treasury = address(0xD0D0);
    address alice = address(0x1);
    address bob   = address(0x2);

    bytes32 constant REGISTRAR = keccak256("REGISTRAR_ROLE");
    bytes32 constant CONTRIB   = keccak256("CONTRIBUTION_ROLE");
    bytes32 constant RETIRE    = keccak256("RETIREMENT_ROLE");

    function setUp() public {
        vm.prank(owner);
        ledger = new CohortLedger(owner, 1e18);
        vm.startPrank(owner);
        ledger.grantRole(REGISTRAR, registrar);
        ledger.grantRole(CONTRIB, treasury);
        ledger.grantRole(RETIRE, owner);
        vm.stopPrank();
    }

    // --- registration -------------------------------------------------------
    function testRegisterAndCohortBucketing() public {
        vm.prank(registrar);
        ledger.registerMember(alice, 1973);
        ICohortLedger.Member memory m = ledger.getMember(alice);
        assertEq(m.birthYear, 1973);
        assertEq(m.cohort, 1970); // (1973/5)*5
        assertTrue(m.active);
        assertEq(ledger.cohortMemberCount(1970), 1);
        assertEq(ledger.totalMembers(), 1);
    }

    function testCannotRegisterTwice() public {
        vm.prank(registrar);
        ledger.registerMember(alice, 1980);
        vm.expectRevert(abi.encodeWithSelector(CohortLedger.AlreadyRegistered.selector, alice));
        vm.prank(registrar);
        ledger.registerMember(alice, 1981);
    }

    function testOnlyRegistrarCanRegister() public {
        vm.expectRevert();
        vm.prank(alice);
        ledger.registerMember(alice, 1980);
    }

    // --- contribution -------------------------------------------------------
    function testContributeMintsPIUs() public {
        vm.prank(registrar);
        ledger.registerMember(alice, 1980);

        vm.prank(treasury);
        uint256 pius = ledger.contribute(alice, 1_000 ether);
        // piusMinted = 1000 * 1e18 / 1e18 = 1000 (1e18-scaled = 1000 PIUs)
        assertEq(pius, 1_000 ether);

        ICohortLedger.Member memory m = ledger.getMember(alice);
        assertEq(m.totalContributions, 1_000 ether);
        assertEq(m.piuBalance, 1_000 ether);
        assertEq(ledger.cohortTotalContributions(1980), 1_000 ether);
    }

    function testContributeRespectsPriceChange() public {
        vm.prank(registrar);
        ledger.registerMember(alice, 1980);
        vm.prank(owner);
        ledger.setPiuPrice(2e18); // PIU worth 2.0

        vm.prank(treasury);
        uint256 pius = ledger.contribute(alice, 4 ether);
        // 4 * 1e18 / 2e18 = 2e18 (i.e. 2 PIUs)
        assertEq(pius, 2 ether);
    }

    function testContributeRevertsIfUnregistered() public {
        vm.expectRevert(abi.encodeWithSelector(CohortLedger.NotRegistered.selector, bob));
        vm.prank(treasury);
        ledger.contribute(bob, 100);
    }

    function testMarkRetiredSetsFlag() public {
        vm.prank(registrar);
        ledger.registerMember(alice, 1960);
        vm.prank(owner);
        ledger.markRetired(alice);
        assertTrue(ledger.getMember(alice).retired);
    }
}
