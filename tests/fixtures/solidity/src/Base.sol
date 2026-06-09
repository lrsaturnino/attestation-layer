// SPDX-License-Identifier: MIT
pragma solidity ^0.8.13;

// Base carries the audit hook and the event the derived vault reuses through inheritance.
contract Base {
    event Redeemed(address indexed account, uint256 amount);

    uint256 internal _auditCount;

    function _audit() internal {
        _auditCount += 1;
    }
}
