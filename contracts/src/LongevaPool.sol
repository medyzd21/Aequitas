// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {ILongevaPool} from "./interfaces/ILongevaPool.sol";
import {IMortalityOracle} from "./interfaces/IMortalityOracle.sol";
import {Owned} from "./utils/Owned.sol";
import {Roles} from "./utils/Roles.sol";

/**
 * @title LongevaPool — tontine-style longevity pool (Longeva).
 * @notice Simple share-based pool denominated in the chain's native asset
 *         (ETH for the MVP — swap to a stablecoin later). Works like a
 *         minimal ERC-4626 vault:
 *
 *             sharesMinted = amount * totalShares / totalAssets
 *                            (if totalShares == 0: sharesMinted = amount)
 *             shareToAssets(s) = s * totalAssets / totalShares
 *
 *         Three ways assets / shares change:
 *           1. `deposit`              — member adds assets, gets shares.
 *           2. `simulateYield`        — admin tops up assets (raises NAV).
 *           3. `releaseMortalityCredit` — oracle confirms death; deceased's
 *              shares are burned, assets STAY in the pool (NAV/share up).
 *              This is the core longevity-credit mechanism.
 *           4. `payTo`                — whitelisted router/backstop pulls
 *              assets out to fund retirement payments.
 *
 *         The off-chain Python engine computes actuarial reserves; this
 *         contract only executes share math and honours oracle deaths.
 */
contract LongevaPool is ILongevaPool, Roles {
    bytes32 public constant DEPOSIT_ROLE  = keccak256("DEPOSIT_ROLE");
    bytes32 public constant PAYOUT_ROLE   = keccak256("PAYOUT_ROLE");
    bytes32 public constant YIELD_ROLE    = keccak256("YIELD_ROLE");

    IMortalityOracle public immutable mortality;

    uint256 public totalAssets;
    uint256 public totalShares;
    mapping(address => uint256) private _shares;

    error ZeroAmount();
    error InsufficientAssets(uint256 requested, uint256 available);
    error NotDeceased(address wallet);
    error NoSharesToRelease(address wallet);
    error InsufficientBalance(uint256 sent, uint256 expected);

    constructor(address initialOwner, IMortalityOracle _mortality) Owned(initialOwner) {
        if (address(_mortality) == address(0)) revert ZeroAddress();
        mortality = _mortality;
    }

    // ------------------------------------------------------------- deposits
    /// @dev `wallet` is the member on whose behalf shares are minted; caller
    ///      must have DEPOSIT_ROLE (typically CohortLedger-linked treasury
    ///      or the member via a wrapper). `msg.value` is the asset amount.
    function deposit(address wallet, uint256 amount)
        external
        payable
        onlyRole(DEPOSIT_ROLE)
    {
        if (amount == 0) revert ZeroAmount();
        if (msg.value != amount) revert InsufficientBalance(msg.value, amount);

        uint256 shares_;
        if (totalShares == 0 || totalAssets == 0) {
            shares_ = amount;
        } else {
            shares_ = (amount * totalShares) / totalAssets;
        }

        _shares[wallet] += shares_;
        totalShares += shares_;
        totalAssets += amount;
        emit Deposited(wallet, amount, shares_);
    }

    // --------------------------------------------------------------- yield
    /// @dev MVP yield source: admin/strategy tops up the pool with assets.
    ///      Real integration later: IERC4626 strategy or Chainlink data-feed
    ///      based yield accrual.
    function simulateYield() external payable onlyRole(YIELD_ROLE) {
        if (msg.value == 0) revert ZeroAmount();
        totalAssets += msg.value;
        emit YieldHarvested(msg.value);
    }

    function harvestYield() external onlyRole(YIELD_ROLE) returns (uint256 minted) {
        // Placeholder — in prod this would pull from a yield source.
        minted = 0;
        emit YieldHarvested(0);
    }

    // ------------------------------------------------------- mortality credit
    /// @dev Anyone can trigger the credit once the oracle has confirmed the
    ///      death — the action is deterministic and verifiable.
    function releaseMortalityCredit(address wallet)
        external
        returns (uint256 assetsReleased)
    {
        if (!mortality.isDeceased(wallet)) revert NotDeceased(wallet);
        uint256 s = _shares[wallet];
        if (s == 0) revert NoSharesToRelease(wallet);

        // Compute NAV equivalent (for the event) BUT keep assets in the pool
        // so surviving shares see a higher NAV — classic tontine.
        assetsReleased = shareToAssets(s);
        _shares[wallet] = 0;
        totalShares -= s;
        emit MortalityCreditReleased(wallet, s, assetsReleased);
    }

    // ----------------------------------------------------------- payouts
    function payTo(address to, uint256 amount) external onlyRole(PAYOUT_ROLE) {
        if (amount == 0) revert ZeroAmount();
        if (amount > totalAssets) revert InsufficientAssets(amount, totalAssets);
        totalAssets -= amount;
        (bool ok, ) = payable(to).call{value: amount}("");
        require(ok, "pay fail");
        emit PaidOut(to, amount);
    }

    // ------------------------------------------------------------- views
    function sharesOf(address wallet) external view returns (uint256) {
        return _shares[wallet];
    }

    function shareToAssets(uint256 shares_) public view returns (uint256) {
        if (totalShares == 0) return 0;
        return (shares_ * totalAssets) / totalShares;
    }

    // Allow the pool to receive unsolicited ETH as a yield top-up.
    receive() external payable {
        totalAssets += msg.value;
        emit YieldHarvested(msg.value);
    }
}
