// SPDX-License-Identifier: MIT
pragma solidity ^0.8.13;

// The ON-CHAIN half of the PC-13 cross-language capstone. A redemption is AUTHORIZED before it is
// finalized: finalize_redemption REVERTS when the wallet is not authorized, so the on-chain
// authorization guard the cross-language requirement names is real in the source, not modeled only.
// The reviewed S (RedemptionVault.tla) is a human's TLA model of exactly this guarantee, and its
// trace-observable projection is validated to reproduce this contract's REAL Foundry traces (PC-11).
//
// The function is named in snake_case (finalize_redemption) so it matches the requirement's action
// identifier across the adapter line: the same token the sub-claim lowers to Pred_finalize_redemption
// and the source impact resolves to a real symbol + call-graph node.
contract RedemptionVault {
    event RedemptionAuthorized(address indexed wallet);
    event RedemptionFinalized(address indexed wallet, uint256 amount);

    mapping(address => bool) public authorized;
    uint256 public finalizedTotal;

    function authorize(address wallet) public {
        authorized[wallet] = true;
        emit RedemptionAuthorized(wallet);
    }

    // Finalize a redemption ONLY out of an authorized state; an unauthorized finalize reverts. The
    // internal _record call is a real intra-contract edge the Slither call graph reconstructs.
    function finalize_redemption(address wallet, uint256 amount) public {
        require(authorized[wallet], "redemption not authorized");
        _record(amount);
        emit RedemptionFinalized(wallet, amount);
    }

    function _record(uint256 amount) internal {
        finalizedTotal += amount;
    }
}
