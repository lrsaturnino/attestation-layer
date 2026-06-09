---- MODULE RedemptionCoordinator ----
\* Reviewed system spec S for the OFF-CHAIN Go redemption coordinator (PC-13 cross-language
\* capstone, Go vertical). Hand-written and reviewed per the PB-5 pattern: a human's TLA model of
\* the coordinator's authorization guarantee, NOT machine-extracted. Its trace-observable
\* projection (a SpecTraceContract over the validate + record stages) is validated to reproduce the
\* coordinator's REAL `go test -trace` runtime traces (PC-11) before it grounds any S /\ R.
\*
\* The coordinator executes a sweep only out of an authorized state. Authorization defaults closed
\* (Pred_authorized == FALSE), so a sweep reached while not-authorized is the forbidden outcome an
\* authorization_precondition requirement forbids. A DISTINCT module from the Solidity vault (its
\* own state variable, its own action predicate) so Pillar B runs S /\ R PER LANGUAGE, never one
\* combined module. Shares the RedemptionAuthorization.tla shape the benchmark corpus proves runs
\* under real apalache-mc.
EXTENDS Naturals, TLC

\* @type: Str;
VARIABLE coordinatorPhase

\* @type: (Str) => Bool;
Pred_authorized(a) == FALSE
\* @type: (Str) => Bool;
Pred_not_authorized(a) == coordinatorPhase \in {"denied", "swept"}
\* @type: (Str) => Bool;
Pred_execute_sweep(a) == coordinatorPhase = "swept"
\* System invariant: the coordinator's authorization defaults closed.
CoordinatorAuthorizationClosed == Pred_authorized("operator") = FALSE
SInit == coordinatorPhase = "init"
SNext == \/ (coordinatorPhase = "init" /\ coordinatorPhase' = "denied")
         \/ (coordinatorPhase = "denied" /\ coordinatorPhase' = "swept")
         \/ UNCHANGED coordinatorPhase
====
