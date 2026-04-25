// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Test} from "forge-std/Test.sol";
import {ActuarialMethodRegistry} from "../src/ActuarialMethodRegistry.sol";
import {ActuarialResultRegistry} from "../src/ActuarialResultRegistry.sol";
import {ActuarialVerifier} from "../src/ActuarialVerifier.sol";
import {IActuarialMethodRegistry} from "../src/interfaces/IActuarialMethodRegistry.sol";
import {IActuarialResultRegistry} from "../src/interfaces/IActuarialResultRegistry.sol";

contract ActuarialProofLayerTest is Test {
    ActuarialMethodRegistry methodRegistry;
    ActuarialResultRegistry resultRegistry;
    ActuarialVerifier verifier;

    address owner = address(0xA11CE);
    address publisher = address(0xBEEF);

    bytes32 constant METHOD_ADMIN_ROLE = keccak256("METHOD_ADMIN_ROLE");
    bytes32 constant PUBLISHER_ROLE = keccak256("PUBLISHER_ROLE");

    function setUp() public {
        vm.prank(owner);
        methodRegistry = new ActuarialMethodRegistry(owner);
        vm.prank(owner);
        resultRegistry = new ActuarialResultRegistry(owner);
        verifier = new ActuarialVerifier();

        vm.startPrank(owner);
        methodRegistry.grantRole(METHOD_ADMIN_ROLE, publisher);
        resultRegistry.grantRole(PUBLISHER_ROLE, publisher);
        vm.stopPrank();
    }

    function testRegisterMethodVersion() public {
        bytes32 methodKey = keccak256("epv_discrete_v1");
        vm.expectEmit(true, true, false, true);
        emit IActuarialMethodRegistry.MethodRegistered(
            methodKey,
            keccak256(bytes("EPV")),
            "EPV",
            "epv_discrete_v1",
            1_777_000_000,
            publisher
        );
        vm.prank(publisher);
        methodRegistry.registerMethod(
            methodKey,
            "EPV",
            "epv_discrete_v1",
            keccak256("spec"),
            keccak256("impl"),
            keccak256("schema"),
            1_777_000_000,
            keccak256("meta"),
            true
        );

        IActuarialMethodRegistry.MethodVersion memory method_ = methodRegistry.getMethod(methodKey);
        assertEq(method_.methodKey, methodKey);
        assertEq(method_.methodFamily, "EPV");
        assertTrue(method_.active);
    }

    function testOnlyAdminCanRegisterMethod() public {
        vm.expectRevert();
        methodRegistry.registerMethod(
            keccak256("x"),
            "EPV",
            "epv_discrete_v1",
            keccak256("spec"),
            keccak256("impl"),
            keccak256("schema"),
            1,
            keccak256("meta"),
            true
        );
    }

    function testPublishParameterAndResultSnapshots() public {
        bytes32 parameterSetKey = keccak256("params");
        bytes32 valuationSnapshotKey = keccak256("valuation");
        bytes32 schemeSummaryKey = keccak256("scheme");
        bytes32 resultBundleKey = keccak256("bundle");

        vm.startPrank(publisher);
        vm.expectEmit(true, false, false, true);
        emit IActuarialResultRegistry.ParameterSetPublished(parameterSetKey, 2026, keccak256("params_hash"), publisher);
        resultRegistry.publishParameterSet(
            parameterSetKey,
            2026,
            300,
            200,
            500,
            1e18,
            500,
            1,
            keccak256("params_hash")
        );
        resultRegistry.publishValuationSnapshot(
            valuationSnapshotKey,
            parameterSetKey,
            keccak256("members"),
            keccak256("cohorts"),
            25,
            6,
            keccak256("inputs")
        );
        resultRegistry.publishSchemeSummary(
            schemeSummaryKey,
            valuationSnapshotKey,
            100e18,
            95e18,
            9500,
            10400,
            keccak256("scheme_hash")
        );
        resultRegistry.publishResultBundle(
            resultBundleKey,
            parameterSetKey,
            valuationSnapshotKey,
            keccak256("mortality"),
            keccak256("epv"),
            keccak256("mwr"),
            keccak256("fairness"),
            schemeSummaryKey,
            keccak256("cohort_digest"),
            keccak256("result_hash")
        );
        vm.stopPrank();

        IActuarialResultRegistry.ParameterSet memory params = resultRegistry.getParameterSet(parameterSetKey);
        assertEq(params.parameterSetKey, parameterSetKey);
        assertEq(params.valuationDate, 2026);

        IActuarialResultRegistry.ResultBundle memory bundle = resultRegistry.getResultBundle(resultBundleKey);
        assertEq(bundle.schemeSummaryKey, schemeSummaryKey);
        assertEq(bundle.publisher, publisher);
    }

    function testVerifyMwrSpotCheck() public {
        (bool passes, uint256 computed, uint256 deviationBps) = verifier.verifyMWR(
            95e18,
            100e18,
            95e16,
            5
        );
        assertTrue(passes);
        assertEq(computed, 95e16);
        assertEq(deviationBps, 0);
    }

    function testVerifyCorridorPassAndFail() public {
        int256[] memory before_ = new int256[](2);
        int256[] memory afterPass_ = new int256[](2);
        int256[] memory afterFail_ = new int256[](2);
        before_[0] = 1000;
        before_[1] = 1000;
        afterPass_[0] = 980;
        afterPass_[1] = 970;
        afterFail_[0] = 900;
        afterFail_[1] = 700;

        (bool passOk, uint256 passDeviation) = verifier.verifyCorridorPass(before_, afterPass_, 1_000, 500);
        assertTrue(passOk);
        assertEq(passDeviation, 100);

        (bool failOk, uint256 failDeviation) = verifier.verifyCorridorPass(before_, afterFail_, 1_000, 500);
        assertFalse(failOk);
        assertEq(failDeviation, 2000);
    }
}
