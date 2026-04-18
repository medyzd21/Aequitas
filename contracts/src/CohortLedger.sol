// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {ICohortLedger} from "./interfaces/ICohortLedger.sol";
import {Owned} from "./utils/Owned.sol";
import {Roles} from "./utils/Roles.sol";

/**
 * @title CohortLedger — on-chain Phase-1 ledger (EquiGen).
 * @author Aequitas
 * @notice Mirrors the responsibilities of `engine.ledger.CohortLedger` but
 *         ONLY the execution bits: who joined, what they contributed, how
 *         many PIUs they hold, what cohort they belong to.
 *
 *         All *actuarial* math (mortality tables, EPVs, annuity factors,
 *         Monte Carlo) stays off-chain in Python. On-chain we need a
 *         tamper-proof, append-only source of truth for membership and
 *         contribution balances that other modules (FairnessGate,
 *         LongevaPool, VestaRouter) can read.
 *
 *         PIU accrual: piusMinted = amount * 1e18 / piuPrice
 *         Cohort bucket: (birthYear / 5) * 5 — same rule as Python.
 */
contract CohortLedger is ICohortLedger, Roles {
    // ---------------------------------------------------------------- roles
    bytes32 public constant REGISTRAR_ROLE = keccak256("REGISTRAR_ROLE");
    bytes32 public constant CONTRIBUTION_ROLE = keccak256("CONTRIBUTION_ROLE");
    bytes32 public constant RETIREMENT_ROLE = keccak256("RETIREMENT_ROLE");

    // --------------------------------------------------------------- state
    /// @dev PIU price in 1e18 fixed-point. 1e18 ≡ 1.0.
    uint256 public piuPrice;

    mapping(address => Member) private _members;
    address[] private _memberList;

    mapping(uint16 => uint256) private _cohortTotal;
    mapping(uint16 => uint256) private _cohortCount;

    // ---------------------------------------------------------------- errs
    error AlreadyRegistered(address wallet);
    error NotRegistered(address wallet);
    error InactiveMember(address wallet);
    error ZeroAmount();
    error InvalidPrice();
    error InvalidBirthYear(uint16 birthYear);

    // --------------------------------------------------------------- ctor
    constructor(address initialOwner, uint256 initialPiuPrice) Owned(initialOwner) {
        if (initialPiuPrice == 0) revert InvalidPrice();
        piuPrice = initialPiuPrice;
    }

    // --------------------------------------------------------- mutators
    function registerMember(address wallet, uint16 birthYear)
        external
        onlyRole(REGISTRAR_ROLE)
    {
        if (wallet == address(0)) revert ZeroAddress();
        if (_members[wallet].birthYear != 0) revert AlreadyRegistered(wallet);
        if (birthYear < 1900 || birthYear > 2100) revert InvalidBirthYear(birthYear);

        uint16 cohort = cohortOf(birthYear);
        _members[wallet] = Member({
            birthYear: birthYear,
            cohort: cohort,
            active: true,
            retired: false,
            totalContributions: 0,
            piuBalance: 0
        });
        _memberList.push(wallet);
        _cohortCount[cohort] += 1;

        emit MemberRegistered(wallet, birthYear, cohort);
    }

    function contribute(address wallet, uint256 amount)
        external
        onlyRole(CONTRIBUTION_ROLE)
        returns (uint256 piusMinted)
    {
        Member storage m = _members[wallet];
        if (m.birthYear == 0) revert NotRegistered(wallet);
        if (!m.active) revert InactiveMember(wallet);
        if (amount == 0) revert ZeroAmount();

        // piusMinted = amount * 1e18 / piuPrice   (1e18-scaled PIU units)
        piusMinted = (amount * 1e18) / piuPrice;
        m.totalContributions += amount;
        m.piuBalance += piusMinted;
        _cohortTotal[m.cohort] += amount;

        emit ContributionRecorded(wallet, amount, piusMinted);
    }

    function setPiuPrice(uint256 newPrice) external onlyOwner {
        if (newPrice == 0) revert InvalidPrice();
        emit PiuPriceUpdated(piuPrice, newPrice);
        piuPrice = newPrice;
    }

    function markRetired(address wallet) external onlyRole(RETIREMENT_ROLE) {
        Member storage m = _members[wallet];
        if (m.birthYear == 0) revert NotRegistered(wallet);
        m.retired = true;
        emit MemberRetired(wallet);
    }

    // ---------------------------------------------------------- views
    function getMember(address wallet) external view returns (Member memory) {
        return _members[wallet];
    }

    function cohortOf(uint16 birthYear) public pure returns (uint16) {
        return uint16((birthYear / 5) * 5);
    }

    function cohortTotalContributions(uint16 cohort) external view returns (uint256) {
        return _cohortTotal[cohort];
    }

    function cohortMemberCount(uint16 cohort) external view returns (uint256) {
        return _cohortCount[cohort];
    }

    function totalMembers() external view returns (uint256) {
        return _memberList.length;
    }

    function memberAt(uint256 index) external view returns (address) {
        return _memberList[index];
    }
}
