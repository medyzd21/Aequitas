// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

interface ILongevaPool {
    event Deposited(address indexed wallet, uint256 amount, uint256 sharesMinted);
    event YieldHarvested(uint256 amount);
    event MortalityCreditReleased(address indexed wallet, uint256 sharesBurned, uint256 assetsReleased);
    event PaidOut(address indexed to, uint256 amount);

    function deposit(address wallet, uint256 amount) external payable;
    function sharesOf(address wallet) external view returns (uint256);
    function totalAssets() external view returns (uint256);
    function totalShares() external view returns (uint256);
    function shareToAssets(uint256 shares) external view returns (uint256);
    function harvestYield() external returns (uint256 minted);
    function releaseMortalityCredit(address wallet) external returns (uint256 assetsReleased);

    /// @notice Pays `amount` of accounting asset to `to`. Caller must be a
    ///         whitelisted payout module (VestaRouter / BackstopVault).
    function payTo(address to, uint256 amount) external;
}
