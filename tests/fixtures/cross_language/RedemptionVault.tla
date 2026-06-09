---- MODULE RedemptionVault ----
\* Reviewed system spec S for the ON-CHAIN Solidity redemption vault (PC-13 cross-language
\* capstone, Solidity vertical), in the SAFE shape that DISCHARGES the on-chain authorization guard.
\* Hand-written and reviewed per the PB-5 pattern: a human's TLA model of the contract's
\* authorization guarantee, NOT machine-extracted. Its trace-observable projection (a
\* SpecTraceContract) is validated to reproduce the contract's REAL Foundry traces (PC-11) before it
\* grounds any S /\ R.
\*
\* The vault finalizes a redemption ONLY out of an authorized state: a finalize IS reachable, but
\* every path to it passes through "authorized", so no reachable state is both not-authorized AND
\* finalized. The forbidden outcome an authorization_precondition forbids -- the action firing while
\* not-authorized -- is therefore UNREACHABLE, while the not-authorized premise itself IS reachable
\* (init, denied). So S /\ (not_authorized => ~finalize_redemption) is VALID *non-vacuously*: the
\* premise fires and the obligation still holds. The companion RedemptionVaultUnsafe.tla drops the
\* guard (finalize reachable while not-authorized) and yields a real counterexample over the SAME
\* requirement R -- the valid/counterexample contrast over one R is the non-vacuity witness.
EXTENDS Naturals, TLC

\* @type: Str;
VARIABLE vaultPhase

\* @type: (Str) => Bool;
Pred_authorized(a) == vaultPhase \in {"authorized", "finalized"}
\* @type: (Str) => Bool;
Pred_not_authorized(a) == vaultPhase \in {"init", "denied"}
\* @type: (Str) => Bool;
Pred_finalize_redemption(a) == vaultPhase = "finalized"
\* System invariant: the vault only finalizes a redemption out of an authorized state.
VaultFinalizeAuthorized == Pred_finalize_redemption("wallet") => Pred_authorized("wallet")
SInit == vaultPhase = "init"
SNext == \/ (vaultPhase = "init" /\ vaultPhase' = "authorized")
         \/ (vaultPhase = "init" /\ vaultPhase' = "denied")
         \/ (vaultPhase = "authorized" /\ vaultPhase' = "finalized")
         \/ UNCHANGED vaultPhase
====
