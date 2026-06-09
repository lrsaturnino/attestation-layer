---- MODULE RedemptionCoordinator ----
\* Reviewed system spec S for the OFF-CHAIN Go redemption coordinator (PC-13 cross-language
\* capstone, Go vertical), in the SAFE shape that DISCHARGES the off-chain authorization guard.
\* Hand-written and reviewed per the PB-5 pattern: a human's TLA model of the coordinator's
\* authorization guarantee, NOT machine-extracted. Its trace-observable projection (a
\* SpecTraceContract) is validated to reproduce the coordinator's REAL `go test -trace` runtime traces
\* (PC-11) before it grounds any S /\ R.
\*
\* The coordinator executes a sweep ONLY out of an authorized state: a sweep IS reachable, but every
\* path to it passes through "authorized", so no reachable state is both not-authorized AND swept. The
\* forbidden outcome an authorization_precondition forbids -- the action firing while not-authorized --
\* is therefore UNREACHABLE, while the not-authorized premise itself IS reachable (init, denied). So
\* S /\ (not_authorized => ~execute_sweep) is VALID *non-vacuously*. A DISTINCT module from the
\* Solidity vault (its own state variable, its own action predicate) so Pillar B runs S /\ R PER
\* LANGUAGE, never one combined module.
EXTENDS Naturals, TLC

\* @type: Str;
VARIABLE coordinatorPhase

\* @type: (Str) => Bool;
Pred_authorized(a) == coordinatorPhase \in {"authorized", "swept"}
\* @type: (Str) => Bool;
Pred_not_authorized(a) == coordinatorPhase \in {"init", "denied"}
\* @type: (Str) => Bool;
Pred_execute_sweep(a) == coordinatorPhase = "swept"
\* System invariant: the coordinator only executes a sweep out of an authorized state.
CoordinatorSweepAuthorized == Pred_execute_sweep("operator") => Pred_authorized("operator")
SInit == coordinatorPhase = "init"
SNext == \/ (coordinatorPhase = "init" /\ coordinatorPhase' = "authorized")
         \/ (coordinatorPhase = "init" /\ coordinatorPhase' = "denied")
         \/ (coordinatorPhase = "authorized" /\ coordinatorPhase' = "swept")
         \/ UNCHANGED coordinatorPhase
====
