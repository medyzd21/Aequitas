// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

interface ICohortLedger {
    struct Member {
        uint16 birthYear;
        uint16 cohort;
        bool active;
        bool retired;
        uint256 totalContributions;
        uint256 piuBalance;
    }

    event MemberRegistered(address indexed wallet, uint16 birthYear, uint16 cohort);
    event ContributionRecorded(address indexed wallet, uint256 amount, uint256 piusMinted);
    event MemberRetired(address indexed wallet);
    event PiuPriceUpdated(uint256 oldPrice, uint256 newPrice);
    event PiuPricePublished(uint256 oldPrice, uint256 newPrice);
    event PiusMinted(address indexed wallet, uint256 contributionAmount, uint256 piusMinted, uint256 price);
    event PiusBurnedForRetirement(address indexed wallet, uint256 piusBurned);

    function registerMember(address wallet, uint16 birthYear) external;
    function contribute(address wallet, uint256 amount) external returns (uint256 piusMinted);
    function setPiuPrice(uint256 newPrice) external;
    function markRetired(address wallet) external;
    function burnPiusForRetirement(address wallet) external returns (uint256 piusBurned);

    function getMember(address wallet) external view returns (Member memory);
    function cohortOf(uint16 birthYear) external pure returns (uint16);
    function cohortTotalContributions(uint16 cohort) external view returns (uint256);
    function cohortMemberCount(uint16 cohort) external view returns (uint256);
    function piuPrice() external view returns (uint256);
    function totalMembers() external view returns (uint256);
}
