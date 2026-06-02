# Milestone Group 2 Formal Closure Core Digest

Milestone group 2 is roadmap Step 2, covering phases 56 through 61. It starts
after Safe Requirement Intake has produced approved controlled text,
translation candidates, provenance, review state, refusal semantics, and a
translation corpus.

## Objective

Group 2 makes the formal verification spine credible. The output should be a
requirement `R` checked against itself and against reviewed system spec `S`,
with explicit valid, counterexample, timeout, unsupported, and needs-review
outcomes. It must also prevent bounded model-checking evidence from being
misrepresented as inductive proof.

## Phase Digest

| Phase | Focus | Core Dependency From Group 1 |
|---:|---|---|
| 56 | Apalache production backend | Approved IR, refusal codes, producer metadata |
| 57 | TLC production backend | Backend agreement and normalized counterexample shape |
| 58 | TLA projection semantics | DSL v3 and provenance to IR nodes |
| 59 | Counterexample normalization | Product refusal surface and provenance graph |
| 60 | Real `S and R` composition | Self-consistency, system registry, coverage reports |
| 61 | Proof-level evidence boundary | Release-bar evidence-label discipline |

## Required Shape

- Formal backends must be invoked through reproducible runner metadata:
  command, working directory, version, options, timeout, bounds, and artifacts.
- Missing tools must return explicit unsupported/tool-missing results.
- Counterexamples must be normalized enough to name requirement, source span,
  backend, command, violated obligation, and raw artifact hash.
- `S and R` composition must preserve existing system invariants and report
  compatible, incompatible, timeout, unsupported, and needs-review outcomes.
- Proof-level evidence must be reserved for actual proof-producing backends.
  Bounded Apalache or TLC results may support `BOUNDED_CHECKED`, not
  `PROVEN_INDUCTIVE`.

## Handoff From Group 1

Group 1 supplies the safe front door and review boundary. Group 2 should consume
only approved controlled text, selected or agreed translation candidates,
source-span provenance, and explicit review/refusal artifacts. It should not
invent new intake trust semantics.

## Main Risks

- Treating bounded model checking as proof.
- Letting Apalache/TLC parser failures appear as successful checks.
- Producing backend-specific counterexamples that product surfaces cannot use.
- Composing `R` against stale or under-selected system specs.
- Reporting `valid` when the correct outcome is unsupported or needs review.

## Non-Goals

- Full proof-assistant integration.
- Complete TLA semantics for every possible IR node.
- Replacement of brownfield spec extraction or trace extraction, which begin in
  group 3.
