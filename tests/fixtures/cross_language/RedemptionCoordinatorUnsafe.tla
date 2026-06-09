---- MODULE RedemptionCoordinatorUnsafe ----
\* The UNSAFE counterpart of RedemptionCoordinator.tla (PC-13 cross-language capstone, Go vertical):
\* a reviewed S that DROPS the off-chain authorization guard, so the same authorization_precondition
\* requirement R does NOT hold over it. Authorization defaults closed (Pred_authorized == FALSE) yet
\* the coordinator still reaches "swept" directly out of "denied", so a state exists that is both
\* not-authorized AND swept -- exactly the forbidden outcome R forbids. Real apalache-mc finds the
\* reachable trace init -> denied -> swept and reports a COUNTEREXAMPLE on
\* (not_authorized => ~execute_sweep). The system invariant it declares (Pred_authorized == FALSE)
\* DOES hold over this S, so the counterexample comes from R, not from the S-invariant. Used by the
\* capstone's Go-side counterexample test to show that EITHER language's real failure leaves the single
\* ProofObject open and blocks the downstream action.
EXTENDS Naturals, TLC

\* @type: Str;
VARIABLE coordinatorPhase

\* @type: (Str) => Bool;
Pred_authorized(a) == FALSE
\* @type: (Str) => Bool;
Pred_not_authorized(a) == coordinatorPhase \in {"denied", "swept"}
\* @type: (Str) => Bool;
Pred_execute_sweep(a) == coordinatorPhase = "swept"
\* System invariant: the coordinator's authorization defaults closed (holds over this S; failure is R's).
CoordinatorAuthorizationClosed == Pred_authorized("operator") = FALSE
SInit == coordinatorPhase = "init"
SNext == \/ (coordinatorPhase = "init" /\ coordinatorPhase' = "denied")
         \/ (coordinatorPhase = "denied" /\ coordinatorPhase' = "swept")
         \/ UNCHANGED coordinatorPhase
====
