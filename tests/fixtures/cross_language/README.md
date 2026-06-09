# Cross-language capstone fixture (PC-13 / SP3)

One requirement whose premises span a real **Solidity contract** and a real **Go coordinator**,
validated as a single `ProofObject` whose closure gates a downstream action. This fixture holds the
cross-language–specific artifacts; the Solidity and Go *source* are reused from the existing real
vertical fixtures (no rebuild).

## The instance (a tBTC-style redemption — domain language lives ONLY here)

A redemption is authorized **on-chain before it is finalized** AND **off-chain before it is swept**:

| Vertical | Real source fixture | Reviewed `S` (here) | Per-language guard (parent obligation conjunct) |
|---|---|---|---|
| Solidity (on-chain vault) | `tests/fixtures/foundry` (Slither + `forge test` traces) | `RedemptionVault.tla` | `obligation.solidity_authorization_guard` — an unauthorized `finalize_redemption` is rejected |
| Go (off-chain coordinator) | `tests/fixtures/go` (gopls/callgraph + `go test -trace`) | `RedemptionCoordinator.tla` | `obligation.go_authorization_guard` — an unauthorized `execute_sweep` is rejected |

tBTC vocabulary (redemption / vault / sweep) stays **above the adapter line**: it appears only in
this fixture's reviewed specs, the parent requirement, and the domain corpus — never in the agnostic
core (`cross_language.py` / `system_composition.py` / `proof_closure.py`), which is domain-free.

## Files

- `requirement.json` — the parent cross-language `RequirementIRV2` (`REQ-XLANG-REDEMPTION-001`). Its
  obligation is an `and` of the two per-language guards above; each guard is a real node carrying a
  `vertical_*` metadata binding.
- `RedemptionVault.tla` — reviewed `S` for the Solidity vault (hand-written per PB-5).
- `RedemptionCoordinator.tla` — reviewed `S` for the Go coordinator (a DISTINCT module: own state
  variable, own action predicate), so Pillar B runs `S ∧ R` **per language**, never one combined
  module.

## How the loop closes (`nlreq.cross_language.close_cross_language_proof`)

1. **A** decomposes the requirement into the two per-language guards (the parent IR).
2. **C** resolves symbols + extracts REAL traces in both languages (Slither/Foundry, gopls/runtime
   trace) and supplies both reviewed `S` specs; each `S` is validated to reproduce its language's real
   traces (PC-11) before it grounds the check.
3. **B** runs a real Apalache `S ∧ R` per language and tags each result with its guard's premise_id.
4. Both results aggregate into ONE `ProofObject` (`build_cross_language_dispatch_plan`, `formal_claim`
   routing so a guard is discharged ONLY by its own language's `BOUNDED_CHECKED` result). The closure
   gates the downstream action (PB-8): it passes only when BOTH guards' `S ∧ R` are valid; a
   counterexample in either language blocks the action.

See `tests/test_cross_language_capstone.py`.
