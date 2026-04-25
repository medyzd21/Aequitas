// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

interface IActuarialMethodRegistry {
    struct MethodVersion {
        bytes32 methodKey;
        string methodFamily;
        string versionLabel;
        bytes32 specHash;
        bytes32 referenceImplHash;
        bytes32 parameterSchemaHash;
        uint64 effectiveDate;
        bytes32 metadataHash;
        address publisher;
        bool active;
    }

    event MethodRegistered(
        bytes32 indexed methodKey,
        bytes32 indexed familyKey,
        string methodFamily,
        string versionLabel,
        uint64 effectiveDate,
        address publisher
    );

    event ActiveMethodUpdated(
        bytes32 indexed familyKey,
        bytes32 indexed methodKey,
        string methodFamily,
        string versionLabel
    );

    function getMethod(bytes32 methodKey) external view returns (MethodVersion memory);

    function activeMethodKey(bytes32 familyKey) external view returns (bytes32);
}
