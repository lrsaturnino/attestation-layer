// SPDX-License-Identifier: MIT
pragma solidity ^0.8.13;

import {Vault} from "../src/Vault.sol";

// A forge-std-free test (so the fixture is hermetic — no submodules or network). It reads `total`,
// performs the redemption, then reads `total` again, so the trace records the pre-state read, the
// Redeemed event, and the post-state read whose return shows the state changed from 0 to 5.
contract VaultTest {
    Vault vault;

    function setUp() public {
        vault = new Vault();
    }

    function test_RedeemedEmittedBeforeStateChange() public {
        uint256 startingTotal = vault.total();
        vault.requestRedemption(5);
        uint256 updatedTotal = vault.total();
        require(startingTotal == 0, "starting total must be zero");
        require(updatedTotal == 5, "updated total must reflect the redemption");
    }
}
