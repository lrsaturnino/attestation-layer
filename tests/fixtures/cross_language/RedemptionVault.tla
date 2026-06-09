---- MODULE RedemptionVault ----
\* Reviewed system spec S for the ON-CHAIN Solidity redemption vault (PC-13 cross-language
\* capstone, Solidity vertical). Hand-written and reviewed per the PB-5 pattern: a human's TLA
\* model of the contract's authorization guarantee, NOT machine-extracted. Its trace-observable
\* projection (a SpecTraceContract over the Redeemed event + the total() read) is validated to
\* reproduce the contract's REAL Foundry traces (PC-11) before it grounds any S /\ R.
\*
\* The vault finalizes a redemption only out of an authorized state. Authorization defaults closed
\* (Pred_authorized == FALSE), so a finalize reached while not-authorized is the forbidden outcome
\* an authorization_precondition requirement forbids. Shares the RedemptionAuthorization.tla shape
\* the benchmark corpus proves runs under real apalache-mc.
EXTENDS Naturals, TLC

\* @type: Str;
VARIABLE vaultPhase

\* @type: (Str) => Bool;
Pred_authorized(a) == FALSE
\* @type: (Str) => Bool;
Pred_not_authorized(a) == vaultPhase \in {"denied", "finalized"}
\* @type: (Str) => Bool;
Pred_finalize_redemption(a) == vaultPhase = "finalized"
\* System invariant: the vault's authorization defaults closed.
VaultAuthorizationClosed == Pred_authorized("wallet") = FALSE
SInit == vaultPhase = "init"
SNext == \/ (vaultPhase = "init" /\ vaultPhase' = "denied")
         \/ (vaultPhase = "denied" /\ vaultPhase' = "finalized")
         \/ UNCHANGED vaultPhase
====
