# Milestone Group 11 Real Formal System Closure Digest

Milestone group 11 implements phases 124 through 130 from
`docs/conclusion-real-evidence-closure-roadmap.md`. It turns formal-system
closure from scaffold-level reports into backend-executed, budget-aware,
counterexample-explaining evidence.

## Roadmap Digest

Group 10 made the front door stricter: raw user language becomes approved
controlled text, controlled text lowers through semantic decomposition, and
semantic agreement and self-consistency fail closed. Group 11 hardens the next
path:

```text
formal claim R -> real backend execution -> reviewed system spec S
-> S and R composition -> counterexample or closure evidence
-> budget/unknown policy -> proof-boundary evidence labels
```

The main release risk is false proof strength. A bounded model checker can
produce useful evidence, but it cannot silently become an inductive theorem.
Timeouts, missing tools, stale specs, unsupported fragments, and parse failures
must block closure or route to review instead of passing.

## Phase Map

| Phase | Theme | Primary implementation |
|---:|---|---|
| 124 | Formal claim semantics completion | `nlreq.formal_claim` semantics completion reference |
| 125 | Production Apalache execution | `nlreq.formal_backend.ApalacheBackend` and model-checker normalization |
| 126 | Production TLC execution | `nlreq.formal_backend.TlcProductionBackend` explicit-state profile |
| 127 | Real `S and R` TLA composition | `nlreq.system_checker` and `nlreq.system_composition` artifact metadata |
| 128 | Counterexample explanation contract | `nlreq.counterexample_normalization` explanation report |
| 129 | Verification budget and unknown policy | `nlreq.verification_budget` closure-effect classification |
| 130 | Proof-producing backend boundary | `nlreq.evidence_boundary` proof-producing backend report |

## Spec And ADR Matrix

| Phase | Spec | ADR | Primary contracts | Verification surface |
|---:|---|---|---|---|
| 124 | `docs/phase-124-formal-claim-semantics-completion.md` | `docs/adr/0133-formal-claim-semantics-completion.md` | exact claim-class semantics, evidence matrix, unsupported behavior | `tests/test_milestone_group11.py` |
| 125 | `docs/phase-125-production-apalache-execution.md` | `docs/adr/0134-apalache-execution-result-normalization.md` | Apalache command metadata, symbolic bounded profile, missing-tool/timeout normalization | `tests/test_milestone_group11.py` |
| 126 | `docs/phase-126-production-tlc-execution.md` | `docs/adr/0135-tlc-execution-result-normalization.md` | TLC command metadata, explicit-state profile, counterexample parsing | `tests/test_milestone_group11.py` |
| 127 | `docs/phase-127-real-s-and-r-tla-composition.md` | `docs/adr/0136-real-s-and-r-tla-composition.md` | reviewed/fresh spec precondition, composed artifact hashes, namespace policy | `tests/test_milestone_group11.py` |
| 128 | `docs/phase-128-counterexample-explanation-contract.md` | `docs/adr/0137-counterexample-explanation-contract.md` | trace steps, violated property, bounds, source-span mapping, Markdown renderer | `tests/test_milestone_group11.py` |
| 129 | `docs/phase-129-verification-budget-unknown-policy.md` | `docs/adr/0138-verification-budget-unknown-policy.md` | non-approving timeout/unknown outcomes, closure effect, reviewed assumptions | `tests/test_milestone_group11.py` |
| 130 | `docs/phase-130-proof-producing-backend-boundary.md` | `docs/adr/0139-proof-producing-backend-boundary.md` | checked proof artifacts, proof-assistant producer requirement, bounded evidence restrictions | `tests/test_milestone_group11.py` |

## Shared Contracts

- Formal claim semantics are machine-readable and complete for every supported
  DSL v3 claim class.
- Backend execution records command, version, bounds, output hashes, artifact
  hashes, and checker profile.
- Apalache and TLC both produce `BOUNDED_CHECKED` evidence only for bounded
  valid or counterexample outcomes.
- Missing tools, parse errors, unsupported fragments, stale specs, and timeouts
  cannot approve closure.
- `S and R` composition reports expose backend-checkable TLA/config artifacts
  when a solver-backed run produced them.
- Counterexample explanations retain backend trace excerpts and map them back
  to formal claim fragments and controlled-text spans where available.
- `PROVEN_INDUCTIVE` requires a proof-assistant producer, valid backend result,
  retained checked proof artifact, and checker command metadata.

## Implemented Schemas

- `schemas/formal-claim-semantics-completion.schema.json`
- `schemas/formal-backend-response.schema.json`
- `schemas/s-and-r-composition-report.schema.json`
- `schemas/counterexample-explanation-report.schema.json`
- `schemas/budgeted-verification-outcome.schema.json`
- `schemas/proof-producing-backend-boundary-report.schema.json`

## Exit Readiness

Group 11 exits when specs and ADRs are accepted, schemas are generated, CLI
commands can emit every new report, `tests/test_milestone_group11.py` passes,
and the broader test suite confirms group 10 translation artifacts remain
compatible with real formal backend closure.
