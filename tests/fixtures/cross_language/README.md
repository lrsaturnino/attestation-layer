# Cross-language capstone fixture (PC-13 / SP3)

One requirement whose premises span a real **Solidity contract** and a real **Go coordinator**,
validated as a single `ProofObject` whose closure gates a downstream action. The source in both
languages REALIZES the requirement's named actions with a real authorization guard, so the reviewed
`S` models what the code actually does — not a paper system.

## The instance (a tBTC-style redemption — domain language lives ONLY here)

A redemption is authorized **on-chain before it is finalized** AND **off-chain before it is swept**:

| Vertical | Real source fixture (here) | Reviewed `S` (here) | Per-language guard (parent obligation conjunct) |
|---|---|---|---|
| Solidity (on-chain vault) | `solidity/` — `finalize_redemption` `require()`s authorization; Slither resolve/call-graph + `forge test` traces | `RedemptionVault.tla` | `obligation.solidity_authorization_guard` — an unauthorized `finalize_redemption` is rejected |
| Go (off-chain coordinator) | `go/` — `execute_sweep` refuses an unauthorized sweep; gopls/CHA call-graph + `go test -trace` | `RedemptionCoordinator.tla` | `obligation.go_authorization_guard` — an unauthorized `execute_sweep` is rejected |

tBTC vocabulary (redemption / vault / sweep) stays **above the adapter line**: it appears only in
this fixture's source, reviewed specs, and the parent requirement — never in the agnostic core
(`cross_language.py` / `system_composition.py` / `proof_closure.py`), which is domain-free.

## Files

- `requirement.json` — the parent cross-language `RequirementIRV2` (`REQ-XLANG-REDEMPTION-001`). Its
  obligation is an `and` of the two per-language guards above; each guard is a real node carrying a
  `vertical_language` / `vertical_adapter` binding AND a `guard_action` / `guard_premise_predicate`
  declaration of which action and precondition it is about.
- `solidity/` — a hermetic Foundry project. `src/RedemptionVault.sol` exposes `finalize_redemption`,
  which `require()`s the wallet is authorized; `test/RedemptionVault.t.sol` drives the authorized
  happy path AND an unauthorized finalize that reverts. The action is named in snake_case so it
  matches the requirement's action identifier across the adapter line.
- `go/` — a Go module. `coordinator/coordinator.go` exposes `execute_sweep`, which consults the
  `Guard` (an interface dispatch CHA resolves) and refuses an unauthorized sweep;
  `coordinator/coordinator_test.go` drives it under `runtime/trace`.
- `RedemptionVault.tla` / `RedemptionCoordinator.tla` — the SAFE reviewed `S` for each vertical
  (hand-written per PB-5). The action is reachable, but ONLY out of an authorized state, so the
  not-authorized premise is reachable while the forbidden outcome (the action firing while
  not-authorized) is unreachable: `S ∧ R` is VALID non-vacuously.
- `RedemptionVaultUnsafe.tla` / `RedemptionCoordinatorUnsafe.tla` — the UNSAFE counterparts that drop
  the guard, so the SAME requirement `R` yields a real apalache counterexample. The valid-vs-
  counterexample contrast over one `R` is the non-vacuity witness, and each is a DISTINCT module
  (own state variable, own action predicate) so Pillar B runs `S ∧ R` per language, never combined.

## How the loop closes (`nlreq.cross_language.close_cross_language_proof`)

1. **A** decomposes the requirement into the two per-language guards (the parent IR). Each vertical's
   sub-claim is bound to its guard's declared action + precondition before any check, so a wrong or
   vacuous sub-claim cannot stand in for the guard.
2. **C** resolves the named action to a real source symbol and builds impact from the REAL call graph
   in both languages (Slither / CHA), and extracts REAL traces (Foundry / `go test -trace`); each
   reviewed `S` is validated to reproduce its language's real traces (PC-11) — for the vault, the
   trace even witnesses the unauthorized finalize reverting — before it grounds the check.
3. **B** runs a real Apalache `S ∧ R` per language (over the parent's "when NOT authorized, reject"
   slice) and tags each result with its guard's premise_id.
4. Both results aggregate into ONE `ProofObject` (`build_cross_language_dispatch_plan`, `formal_claim`
   routing so a guard is discharged ONLY by its own language's `BOUNDED_CHECKED` result). The closure
   gates the downstream action (PB-8): it passes only when BOTH guards' `S ∧ R` are valid; a real
   counterexample in EITHER language blocks the action.

See `tests/test_cross_language_capstone.py`.
