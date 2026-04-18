// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {IMortalityOracle} from "./interfaces/IMortalityOracle.sol";
import {Owned} from "./utils/Owned.sol";
import {Roles} from "./utils/Roles.sol";

/**
 * @title MortalityOracle — operator-gated death confirmation (Longeva).
 * @notice MVP: authorised operators (hospitals, national registries, a
 *         multisig) can confirm a death, optionally attaching a hash of an
 *         off-chain proof document. Everyone else reads via `isDeceased`.
 *
 *         Later: replace with a decentralised oracle network (Chainlink
 *         Functions pulling from a national death registry), zk-proof of
 *         certificate validity, or DAO-governed challenge period.
 */
contract MortalityOracle is IMortalityOracle, Roles {
    bytes32 public constant ORACLE_ROLE = keccak256("ORACLE_ROLE");

    mapping(address => uint64) private _deathTs;
    mapping(address => bytes32) public proof;

    error AlreadyDeceased(address wallet);
    error NotKnownDead(address wallet);

    constructor(address initialOwner) Owned(initialOwner) {}

    function confirmDeath(address wallet, uint64 deathTimestamp, bytes32 proofHash)
        external
        onlyRole(ORACLE_ROLE)
    {
        if (wallet == address(0)) revert ZeroAddress();
        if (_deathTs[wallet] != 0) revert AlreadyDeceased(wallet);
        if (deathTimestamp == 0 || deathTimestamp > block.timestamp) {
            deathTimestamp = uint64(block.timestamp);
        }
        _deathTs[wallet] = deathTimestamp;
        proof[wallet] = proofHash;
        emit DeathConfirmed(wallet, deathTimestamp, proofHash);
    }

    function revokeDeath(address wallet) external onlyOwner {
        if (_deathTs[wallet] == 0) revert NotKnownDead(wallet);
        _deathTs[wallet] = 0;
        proof[wallet] = bytes32(0);
        emit DeathRevoked(wallet);
    }

    function isDeceased(address wallet) external view returns (bool) {
        return _deathTs[wallet] != 0;
    }

    function deathTimestamp(address wallet) external view returns (uint64) {
        return _deathTs[wallet];
    }
}
