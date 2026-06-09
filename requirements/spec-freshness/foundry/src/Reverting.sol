// SPDX-License-Identifier: MIT
pragma solidity ^0.8.13;

// Child.willRevert always reverts. Caller.attempt invokes it through a low-level call so the revert
// is observable as a nested, failed sub-call WITHOUT propagating — the calling test stays green
// while the real EVM trace records a success=false frame one level below a successful parent. This
// is the nested/external call path + revert the trace projection must preserve.
contract Child {
    function willRevert() external pure {
        revert("child reverted");
    }
}

contract Caller {
    Child public child;

    constructor() {
        child = new Child();
    }

    function attempt() external returns (bool ok) {
        (ok, ) = address(child).call(abi.encodeWithSignature("willRevert()"));
    }
}
