---- MODULE RedemptionVaultUnsafe ----
\* The UNSAFE counterpart of RedemptionVault.tla (PC-13 cross-language capstone, Solidity vertical):
\* a reviewed S that DROPS the on-chain authorization guard, so the same authorization_precondition
\* requirement R does NOT hold over it. Authorization defaults closed (Pred_authorized == FALSE) yet
\* the vault still reaches "finalized" directly out of "denied", so a state exists that is both
\* not-authorized AND finalized -- exactly the forbidden outcome R forbids. Real apalache-mc finds the
\* reachable trace init -> denied -> finalized and reports a COUNTEREXAMPLE on
\* (not_authorized => ~finalize_redemption). The system invariant it declares
\* (Pred_authorized == FALSE) DOES hold over this S, so the counterexample comes from R, not from the
\* S-invariant. Used by the capstone's counterexample test to show a real per-language failure leaves
\* the single ProofObject open and blocks the downstream action.
EXTENDS Naturals, TLC

\* @type: Str;
VARIABLE vaultPhase

\* @type: (Str) => Bool;
Pred_authorized(a) == FALSE
\* @type: (Str) => Bool;
Pred_not_authorized(a) == vaultPhase \in {"denied", "finalized"}
\* @type: (Str) => Bool;
Pred_finalize_redemption(a) == vaultPhase = "finalized"
\* System invariant: the vault's authorization defaults closed (holds over this S; the failure is R's).
VaultAuthorizationClosed == Pred_authorized("wallet") = FALSE
SInit == vaultPhase = "init"
SNext == \/ (vaultPhase = "init" /\ vaultPhase' = "denied")
         \/ (vaultPhase = "denied" /\ vaultPhase' = "finalized")
         \/ UNCHANGED vaultPhase
====
