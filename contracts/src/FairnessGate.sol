// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {IFairnessGate} from "./interfaces/IFairnessGate.sol";
import {Owned} from "./utils/Owned.sol";
import {Roles} from "./utils/Roles.sol";

/**
 * @title FairnessGate — on-chain enforcement of the intergenerational
 *        fairness corridor (EquiGen).
 * @notice The economic question (“what are the cohort EPVs?”) is answered
 *         off-chain by the Python engine (`engine.ledger.cohort_valuation`).
 *         This contract is just the execution gate: it stores the last
 *         accepted baseline and evaluates any proposed new EPV vector
 *         against the pairwise corridor rule
 *
 *             max_{i,j} |ΔEPV_i − ΔEPV_j| / benchmark ≤ δ
 *
 *         where ΔEPV_c = new_c − baseline_c and benchmark is the mean of
 *         |baseline|. EPVs are passed in 1e18 fixed-point.
 */
contract FairnessGate is IFairnessGate, Roles {
    bytes32 public constant BASELINE_ROLE = keccak256("BASELINE_ROLE");
    bytes32 public constant PROPOSER_ROLE = keccak256("PROPOSER_ROLE");

    mapping(uint16 => int256) private _baseline;
    uint16[] private _baselineCohorts;

    Proposal[] private _proposals;

    error LengthMismatch();
    error EmptyCohorts();
    error DeltaTooHigh(uint256 delta);
    error NoBaselineForCohort(uint16 cohort);

    constructor(address initialOwner) Owned(initialOwner) {}

    // -------------------------------------------------------- baseline
    function setBaseline(uint16[] calldata cohorts, int256[] calldata epvs)
        external
        onlyRole(BASELINE_ROLE)
    {
        if (cohorts.length != epvs.length) revert LengthMismatch();
        if (cohorts.length == 0) revert EmptyCohorts();

        // clear previous
        for (uint256 i = 0; i < _baselineCohorts.length; i++) {
            delete _baseline[_baselineCohorts[i]];
        }
        delete _baselineCohorts;

        for (uint256 i = 0; i < cohorts.length; i++) {
            _baseline[cohorts[i]] = epvs[i];
            _baselineCohorts.push(cohorts[i]);
        }
        emit BaselineSet(cohorts, epvs);
    }

    function baselineEpv(uint16 cohort) external view returns (int256) {
        return _baseline[cohort];
    }

    // ------------------------------------------------------- proposals
    function submitAndEvaluate(
        string calldata name,
        uint16[] calldata cohorts,
        int256[] calldata newEpvs,
        uint256 delta
    )
        external
        onlyRole(PROPOSER_ROLE)
        returns (uint256 id, bool passes)
    {
        if (cohorts.length != newEpvs.length) revert LengthMismatch();
        if (cohorts.length == 0) revert EmptyCohorts();
        if (delta > 1e18) revert DeltaTooHigh(delta);

        // Snapshot proposal
        id = _proposals.length;
        _proposals.push();
        Proposal storage p = _proposals[id];
        p.name = name;
        p.proposer = msg.sender;
        p.submittedAt = uint64(block.timestamp);
        p.delta = delta;
        for (uint256 i = 0; i < cohorts.length; i++) {
            p.cohorts.push(cohorts[i]);
            p.newEpvs.push(newEpvs[i]);
        }
        emit ProposalSubmitted(id, name, msg.sender);

        // Evaluate corridor -------------------------------------------------
        (bool ok, uint256 maxDev, uint16 wa, uint16 wb) = _evaluate(cohorts, newEpvs, delta);
        p.accepted = ok;
        emit ProposalEvaluated(id, ok, maxDev, wa, wb);

        if (ok) {
            // update baseline to accepted state
            for (uint256 i = 0; i < cohorts.length; i++) {
                _baseline[cohorts[i]] = newEpvs[i];
            }
            _baselineCohorts = cohorts;
            emit ProposalAccepted(id);
        } else {
            emit ProposalRejected(id);
        }
        passes = ok;
    }

    // ----------------------------------------------------- evaluation
    /// @dev The corridor check is done with int256 arithmetic for signed
    ///      ΔEPVs and a 1e18-scaled benchmark. See contract-level docs.
    function _evaluate(uint16[] calldata cohorts, int256[] calldata newEpvs, uint256 delta)
        internal
        view
        returns (bool passes, uint256 maxDeviation, uint16 worstA, uint16 worstB)
    {
        // Compute ΔEPV_c for every cohort and the benchmark (mean |baseline|)
        int256[] memory deltas = new int256[](cohorts.length);
        uint256 benchmarkSum;
        for (uint256 i = 0; i < cohorts.length; i++) {
            int256 old = _baseline[cohorts[i]];
            if (old == 0) revert NoBaselineForCohort(cohorts[i]);
            deltas[i] = newEpvs[i] - old;
            benchmarkSum += old >= 0 ? uint256(old) : uint256(-old);
        }
        uint256 benchmark = benchmarkSum / cohorts.length;
        if (benchmark == 0) benchmark = 1; // avoid /0; this is degenerate

        maxDeviation = 0;
        for (uint256 i = 0; i < cohorts.length; i++) {
            for (uint256 j = i + 1; j < cohorts.length; j++) {
                int256 diff = deltas[i] - deltas[j];
                uint256 abs_ = diff >= 0 ? uint256(diff) : uint256(-diff);
                // dev_ij = |Δi − Δj| / benchmark   (1e18-scaled)
                uint256 dev = (abs_ * 1e18) / benchmark;
                if (dev > maxDeviation) {
                    maxDeviation = dev;
                    worstA = cohorts[i];
                    worstB = cohorts[j];
                }
            }
        }
        passes = maxDeviation <= delta;
    }

    // ----------------------------------------------------------- views
    function proposalCount() external view returns (uint256) {
        return _proposals.length;
    }

    function getProposal(uint256 id) external view returns (Proposal memory) {
        return _proposals[id];
    }
}
