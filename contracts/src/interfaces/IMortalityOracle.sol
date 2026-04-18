// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

interface IMortalityOracle {
    event DeathConfirmed(address indexed wallet, uint64 deathTimestamp, bytes32 proofHash);
    event DeathRevoked(address indexed wallet);

    /// @notice True if the oracle has recorded a death for `wallet`.
    function isDeceased(address wallet) external view returns (bool);
    function deathTimestamp(address wallet) external view returns (uint64);
    function confirmDeath(address wallet, uint64 deathTimestamp, bytes32 proofHash) external;
    function revokeDeath(address wallet) external;
}
