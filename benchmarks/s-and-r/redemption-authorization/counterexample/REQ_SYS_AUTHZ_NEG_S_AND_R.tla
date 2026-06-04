---- MODULE REQ_SYS_AUTHZ_NEG_S_AND_R ----
EXTENDS Naturals, TLC

CONSTANT
  \* @type: Str;
  redemption,
  \* @type: Str;
  wallet

VARIABLE
  \* @type: Str;
  authPhase

\* ===== Reviewed system spec S (inlined; operators keep their names) =====
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

\* ===== Requirement R narrows S: a state invariant over S's own variables. R adds
\* no transitions and no variable — S's Init/Next are the only state machine. The
\* obligation forbids S reaching the accepted/executed outcome (Pred_finalize_redemption)
\* while the premise holds, so a counterexample is a real S behavior — not an artifact
\* of a requirement harness stepping its own state. =====
R_Requirement == Pred_not_authorized(wallet) => ~Pred_finalize_redemption(wallet)

\* ===== S ∧ R: S's reachable states must preserve S's invariants and R's obligation =====
Init == SInit
Next == SNext
Inv == AuthorizationDefaultsClosed /\ R_Requirement
ConstInit == redemption = "redemption" /\ wallet = "wallet"
====
