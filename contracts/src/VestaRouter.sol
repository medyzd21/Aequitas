// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {ILongevaPool} from "./interfaces/ILongevaPool.sol";
import {ICohortLedger} from "./interfaces/ICohortLedger.sol";
import {BenefitStreamer} from "./BenefitStreamer.sol";
import {Owned} from "./utils/Owned.sol";
import {Roles} from "./utils/Roles.sol";

/**
 * @title VestaRouter — moves assets from LongevaPool into BenefitStreamer
 *        and starts retirement streams for members marked retired in the
 *        CohortLedger.
 *
 *         Python side computes the annual benefit the actuarial engine
 *         promises each retiree (a function of their PIU balance, pool NAV,
 *         annuity rate at retirement, and discount rate). On-chain we only
 *         execute: "pull N wei out of Longeva, fund Vesta, open a stream".
 */
contract VestaRouter is Roles {
    bytes32 public constant OPERATOR_ROLE = keccak256("OPERATOR_ROLE");

    ICohortLedger public immutable ledger;
    ILongevaPool public immutable pool;
    BenefitStreamer public immutable streamer;

    event RetirementOpened(
        address indexed retiree,
        uint256 fundingPulled,
        uint128 annualBenefit,
        uint64 startTs
    );

    error MemberNotRetired(address wallet);

    constructor(
        address initialOwner,
        ICohortLedger _ledger,
        ILongevaPool _pool,
        BenefitStreamer _streamer
    ) Owned(initialOwner) {
        if (
            address(_ledger) == address(0)
                || address(_pool) == address(0)
                || address(_streamer) == address(0)
        ) revert ZeroAddress();
        ledger = _ledger;
        pool = _pool;
        streamer = _streamer;
    }

    /// @notice Opens a retirement stream for `retiree`. Pulls
    ///         `initialFunding` from LongevaPool into this router, forwards
    ///         it into the streamer as funding, and opens the stream at
    ///         `annualBenefit`. Caller must be OPERATOR_ROLE.
    function openRetirement(
        address retiree,
        uint256 initialFunding,
        uint128 annualBenefit,
        uint64 startTs
    ) external onlyRole(OPERATOR_ROLE) {
        ICohortLedger.Member memory m = ledger.getMember(retiree);
        if (!m.retired) revert MemberNotRetired(retiree);

        // pull funding from longevity pool
        pool.payTo(address(this), initialFunding);

        // forward to streamer (this contract must hold FUNDER_ROLE there)
        streamer.fund{value: initialFunding}();

        // open the stream
        streamer.startStream(retiree, annualBenefit, startTs);

        emit RetirementOpened(retiree, initialFunding, annualBenefit, startTs);
    }

    /// @notice Top-up a stream mid-retirement (e.g. after pool yield).
    function topUp(uint256 amount) external onlyRole(OPERATOR_ROLE) {
        pool.payTo(address(this), amount);
        streamer.fund{value: amount}();
    }

    receive() external payable {}
}
