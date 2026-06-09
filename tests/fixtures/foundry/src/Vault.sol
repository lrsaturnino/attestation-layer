// SPDX-License-Identifier: MIT
pragma solidity ^0.8.13;

// The redemption emits the Redeemed event BEFORE it mutates `total`, so a real execution trace
// must show the event ahead of the observable state change.
contract Vault {
    event Redeemed(address indexed account, uint256 amount);

    uint256 public total;

    function requestRedemption(uint256 amount) public {
        emit Redeemed(msg.sender, amount);
        total += amount;
    }
}
