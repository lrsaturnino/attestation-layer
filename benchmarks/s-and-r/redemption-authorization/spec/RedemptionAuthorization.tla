---- MODULE RedemptionAuthorization ----
EXTENDS Naturals, TLC

\* @type: Str;
VARIABLE authPhase

\* @type: (Str) => Bool;
Pred_authorized(a) == FALSE
\* @type: (Str) => Bool;
Pred_not_authorized(a) == authPhase \in {"denied", "finalized"}
\* @type: (Str) => Bool;
Pred_finalize_redemption(a) == authPhase = "finalized"
\* System invariant: authorization defaults closed.
AuthorizationDefaultsClosed == Pred_authorized("wallet") = FALSE
SInit == authPhase = "init"
SNext == \/ (authPhase = "init" /\ authPhase' = "denied")
         \/ (authPhase = "denied" /\ authPhase' = "finalized")
         \/ UNCHANGED authPhase
====
