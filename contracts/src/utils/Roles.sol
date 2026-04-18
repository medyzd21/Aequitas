// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Owned} from "./Owned.sol";

/// @title Roles — lightweight role mapping on top of Owned.
/// @notice A role is just a bytes32 id. Owner grants/revokes. Contracts use
///         `onlyRole(ROLE)` to gate functions. No external dependency.
abstract contract Roles is Owned {
    mapping(bytes32 => mapping(address => bool)) private _has;

    event RoleGranted(bytes32 indexed role, address indexed account);
    event RoleRevoked(bytes32 indexed role, address indexed account);

    error MissingRole(bytes32 role, address account);

    modifier onlyRole(bytes32 role) {
        if (!_has[role][msg.sender]) revert MissingRole(role, msg.sender);
        _;
    }

    function hasRole(bytes32 role, address account) public view returns (bool) {
        return _has[role][account];
    }

    function grantRole(bytes32 role, address account) external onlyOwner {
        if (!_has[role][account]) {
            _has[role][account] = true;
            emit RoleGranted(role, account);
        }
    }

    function revokeRole(bytes32 role, address account) external onlyOwner {
        if (_has[role][account]) {
            _has[role][account] = false;
            emit RoleRevoked(role, account);
        }
    }
}
