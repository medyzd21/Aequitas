// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {IMortalityOracle} from "./interfaces/IMortalityOracle.sol";
import {Owned} from "./utils/Owned.sol";
import {Roles} from "./utils/Roles.sol";

/**
 * @title BenefitStreamer — per-second retirement income stream (Vesta).
 * @notice For each retiree we store an annual benefit rate. Accrual is
 *         linear in time while the retiree is alive (mortality oracle view).
 *         Retirees pull by calling `claim()`.
 *
 *             accrual(t) = annualBenefit * (t - lastClaim) / SECONDS_PER_YEAR
 *
 *         Actual transfer happens by the streamer pulling from a funded
 *         balance (filled by VestaRouter). On confirmed death the stream
 *         freezes at the death timestamp.
 */
contract BenefitStreamer is Roles {
    uint64 public constant SECONDS_PER_YEAR = 365 days;
    bytes32 public constant STREAM_ADMIN_ROLE = keccak256("STREAM_ADMIN_ROLE");
    bytes32 public constant FUNDER_ROLE = keccak256("FUNDER_ROLE");

    IMortalityOracle public immutable mortality;

    struct Stream {
        uint128 annualBenefit; // wei per year
        uint64 startTs;
        uint64 lastClaimTs;
        uint256 totalClaimed;
        bool active;
    }

    mapping(address => Stream) public streams;
    uint256 public fundedBalance; // ETH received for payouts

    event StreamStarted(address indexed retiree, uint128 annualBenefit, uint64 startTs);
    event StreamStopped(address indexed retiree);
    event Claimed(address indexed retiree, uint256 amount);
    event Funded(uint256 amount, uint256 newBalance);

    error NoStream(address retiree);
    error StreamAlreadyExists(address retiree);
    error NothingToClaim(address retiree);
    error InsufficientFunding(uint256 needed, uint256 available);

    constructor(address initialOwner, IMortalityOracle _mortality) Owned(initialOwner) {
        if (address(_mortality) == address(0)) revert ZeroAddress();
        mortality = _mortality;
    }

    // ------------------------------------------------------- stream admin
    function startStream(address retiree, uint128 annualBenefit, uint64 startTs)
        external
        onlyRole(STREAM_ADMIN_ROLE)
    {
        if (retiree == address(0)) revert ZeroAddress();
        if (streams[retiree].active) revert StreamAlreadyExists(retiree);
        if (startTs == 0) startTs = uint64(block.timestamp);
        streams[retiree] = Stream({
            annualBenefit: annualBenefit,
            startTs: startTs,
            lastClaimTs: startTs,
            totalClaimed: 0,
            active: true
        });
        emit StreamStarted(retiree, annualBenefit, startTs);
    }

    function stopStream(address retiree) external onlyRole(STREAM_ADMIN_ROLE) {
        Stream storage s = streams[retiree];
        if (!s.active) revert NoStream(retiree);
        s.active = false;
        emit StreamStopped(retiree);
    }

    // ---------------------------------------------------------- funding
    function fund() external payable onlyRole(FUNDER_ROLE) {
        fundedBalance += msg.value;
        emit Funded(msg.value, fundedBalance);
    }

    // ------------------------------------------------------------- claim
    /// @notice Pulls accrued benefit up to the current time (or death ts).
    function claim() external returns (uint256 amount) {
        Stream storage s = streams[msg.sender];
        if (!s.active) revert NoStream(msg.sender);

        uint64 cutoff = uint64(block.timestamp);
        if (mortality.isDeceased(msg.sender)) {
            uint64 d = mortality.deathTimestamp(msg.sender);
            if (d < cutoff) cutoff = d;
            s.active = false;
            emit StreamStopped(msg.sender);
        }

        uint64 last = s.lastClaimTs;
        if (cutoff <= last) revert NothingToClaim(msg.sender);

        uint64 elapsed = cutoff - last;
        amount = (uint256(s.annualBenefit) * elapsed) / SECONDS_PER_YEAR;
        if (amount == 0) revert NothingToClaim(msg.sender);
        if (amount > fundedBalance) revert InsufficientFunding(amount, fundedBalance);

        s.lastClaimTs = cutoff;
        s.totalClaimed += amount;
        fundedBalance -= amount;

        (bool ok, ) = payable(msg.sender).call{value: amount}("");
        require(ok, "transfer fail");
        emit Claimed(msg.sender, amount);
    }

    function claimable(address retiree) external view returns (uint256) {
        Stream memory s = streams[retiree];
        if (!s.active) return 0;
        uint64 cutoff = uint64(block.timestamp);
        if (mortality.isDeceased(retiree)) {
            uint64 d = mortality.deathTimestamp(retiree);
            if (d < cutoff) cutoff = d;
        }
        if (cutoff <= s.lastClaimTs) return 0;
        return (uint256(s.annualBenefit) * (cutoff - s.lastClaimTs)) / SECONDS_PER_YEAR;
    }

    receive() external payable {
        // Allow raw ETH top-ups (treated as funding)
        fundedBalance += msg.value;
        emit Funded(msg.value, fundedBalance);
    }
}
