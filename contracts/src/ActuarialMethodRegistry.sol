// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {IActuarialMethodRegistry} from "./interfaces/IActuarialMethodRegistry.sol";
import {Owned} from "./utils/Owned.sol";
import {Roles} from "./utils/Roles.sol";

/**
 * @title ActuarialMethodRegistry
 * @notice Versioned registry for published actuarial methodology metadata.
 *
 * The full actuarial engine stays off-chain in Python. This registry stores
 * only the publicly inspectable proof surface:
 *
 * - method family and version label,
 * - spec / reference implementation / parameter-schema hashes,
 * - effective date,
 * - the currently active version per family.
 *
 * The goal is to prevent silent rewriting of methodology after a published
 * valuation, fairness baseline, or stress result.
 */
contract ActuarialMethodRegistry is IActuarialMethodRegistry, Roles {
    bytes32 public constant METHOD_ADMIN_ROLE = keccak256("METHOD_ADMIN_ROLE");

    mapping(bytes32 => MethodVersion) private _methods;
    mapping(bytes32 => bytes32) public activeMethodKey;

    error InvalidParams();
    error MethodAlreadyExists(bytes32 methodKey);
    error UnknownMethod(bytes32 methodKey);

    constructor(address initialOwner) Owned(initialOwner) {}

    function registerMethod(
        bytes32 methodKey_,
        string calldata methodFamily,
        string calldata versionLabel,
        bytes32 specHash,
        bytes32 referenceImplHash,
        bytes32 parameterSchemaHash,
        uint64 effectiveDate,
        bytes32 metadataHash,
        bool activate
    ) external onlyRole(METHOD_ADMIN_ROLE) {
        if (methodKey_ == bytes32(0)) revert InvalidParams();
        if (bytes(methodFamily).length == 0 || bytes(versionLabel).length == 0) revert InvalidParams();
        if (_methods[methodKey_].methodKey != bytes32(0)) revert MethodAlreadyExists(methodKey_);

        MethodVersion memory version_ = MethodVersion({
            methodKey: methodKey_,
            methodFamily: methodFamily,
            versionLabel: versionLabel,
            specHash: specHash,
            referenceImplHash: referenceImplHash,
            parameterSchemaHash: parameterSchemaHash,
            effectiveDate: effectiveDate,
            metadataHash: metadataHash,
            publisher: msg.sender,
            active: false
        });
        _methods[methodKey_] = version_;

        bytes32 familyKey = keccak256(bytes(methodFamily));
        emit MethodRegistered(methodKey_, familyKey, methodFamily, versionLabel, effectiveDate, msg.sender);

        if (activate) {
            _setActiveMethod(familyKey, methodKey_);
        }
    }

    function setActiveMethod(bytes32 methodKey_) external onlyRole(METHOD_ADMIN_ROLE) {
        MethodVersion storage version_ = _methods[methodKey_];
        if (version_.methodKey == bytes32(0)) revert UnknownMethod(methodKey_);
        bytes32 familyKey = keccak256(bytes(version_.methodFamily));
        _setActiveMethod(familyKey, methodKey_);
    }

    function getMethod(bytes32 methodKey_) external view returns (MethodVersion memory) {
        return _methods[methodKey_];
    }

    function _setActiveMethod(bytes32 familyKey, bytes32 methodKey_) internal {
        bytes32 previous = activeMethodKey[familyKey];
        if (previous != bytes32(0)) {
            _methods[previous].active = false;
        }
        _methods[methodKey_].active = true;
        activeMethodKey[familyKey] = methodKey_;
        emit ActiveMethodUpdated(
            familyKey,
            methodKey_,
            _methods[methodKey_].methodFamily,
            _methods[methodKey_].versionLabel
        );
    }
}
