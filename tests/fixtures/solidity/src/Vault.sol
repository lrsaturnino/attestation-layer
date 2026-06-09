// SPDX-License-Identifier: MIT
pragma solidity ^0.8.13;

import "./Base.sol";

// Vault inherits _audit and Redeemed from Base, and overloads withdraw by argument type. Both
// overloads call the inherited _audit, so the real call graph crosses the inheritance boundary —
// something lexical regex extraction cannot resolve.
contract Vault is Base {
    uint256 public total;

    function withdraw(uint256 amount) public {
        _audit();
        emit Redeemed(msg.sender, amount);
        total -= amount;
    }

    function withdraw(address account) public {
        _audit();
        emit Redeemed(account, 0);
    }
}
