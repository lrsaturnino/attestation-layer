// SPDX-License-Identifier: MIT
pragma solidity ^0.8.13;

import {RedemptionVault} from "../src/RedemptionVault.sol";

// A forge-std-free test (so the fixture is hermetic — no submodules or network). It authorizes the
// wallet, reads finalizedTotal, finalizes the redemption, then reads finalizedTotal again, so the
// real trace records the RedemptionAuthorized event, the RedemptionFinalized event, and the
// post-state read whose return shows finalizedTotal moved from 0 to 5.
contract RedemptionVaultTest {
    RedemptionVault vault;
    address constant WALLET = address(0xBEEF);

    function setUp() public {
        vault = new RedemptionVault();
    }

    function test_AuthorizedRedemptionFinalizes() public {
        uint256 startingTotal = vault.finalizedTotal();
        vault.authorize(WALLET);
        vault.finalize_redemption(WALLET, 5);
        uint256 updatedTotal = vault.finalizedTotal();
        require(startingTotal == 0, "starting total must be zero");
        require(updatedTotal == 5, "updated total must reflect the finalized redemption");
    }

    // An unauthorized finalize must revert. The low-level call keeps the revert observable as a failed
    // sub-call WITHOUT propagating, so the test stays green while the real trace records the rejection.
    function test_UnauthorizedFinalizeReverts() public {
        (bool ok, ) = address(vault).call(
            abi.encodeWithSignature("finalize_redemption(address,uint256)", address(0xCAFE), 7)
        );
        require(!ok, "unauthorized finalize must revert");
    }
}
