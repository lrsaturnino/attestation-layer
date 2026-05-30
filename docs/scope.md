# Scope and Non-Goals

This document states, in one place, what the NL Requirement Attestation Layer
does and — more importantly — what it deliberately does not do in its current
implementation. It consolidates boundaries that are otherwise spread across the
build plan, the per-phase notes, and `future-adapter-routing.md`.

Guiding principle: the layer is a **deterministic attester of individual
controlled-NL requirements**. The reviewed requirement is the trusted anchor and
the tool checks conformance to it. It is not a planner, an analyzer of existing
systems, or a code generator.

## In Scope

- Parse a controlled-NL requirement into typed IR with source-span provenance.
- Resolve its symbols against a configured adapter — the generic vocabulary, or
  a target artifact (Python, OpenAPI, GraphQL, JSON Schema, AsyncAPI,
  Protobuf/gRPC, command/test runner, TLA model, runtime traces).
- Gather graded evidence per requirement: statically resolved, consistency
  checked, SMT checked, and test/contract/bounded/trace evidence where a target
  exists.
- Decide a deterministic status per requirement and emit an immutable, hashed
  package.
- Aggregate per-requirement statuses into report-only indexes, CI reports, soft
  and hard gates, and continuous-attestation runs.
- Emit handoff artifacts (implementation contract sheet, agent work order,
  verifier handoff, audit log) for an external orchestrator, agent, or human to
  consume.

See `README.md` and `adding-a-requirement.md` for the command-level workflow.

## Out of Scope (Current Implementation)

### Reasoning across requirements

Each requirement is attested in isolation. There is no joint or global
consistency check: the layer never combines multiple requirements into a
composite claim, and it will not detect a contradiction *between* two
requirements (for example, one requiring an action to succeed and another
requiring the same action to be rejected). Contradiction detection operates only
*within* a single requirement's conditions. Cross-requirement and cross-system
consistency remain the responsibility of human review and any upstream planner.
Cross-system scope is also called out in `build-plan.md`, and cross-adapter
requirements in `phase-7-openapi-adapter.md`.

### Requirement decomposition and implementation planning

The layer does not break a requirement into implementation sub-steps, generate a
build plan, or sequence work. Decomposition is expected to happen upstream:
author small, atomic requirements (one claim each). The `agent-task` work order
bundles the requirement ids you provide within author-specified `allowed_paths`;
it does not subdivide them.

### Code generation and agent execution

The tool contains no LLM, agent, or network client, and writes no implementation
code. Every package records that no LLM rewrote the controlled text. The
`agent-*` commands build artifacts *for* an external coder or verifier agent;
they do not invoke one. The only subprocess calls are deterministic evidence
backends (test runners and the model checker).

### Impact, regression, and dependency analysis of an existing system

The layer has no model of a target system beyond the requirements written
against it, and performs no dependency, impact, or blast-radius analysis. Its
regression coverage equals its requirement coverage: re-validation
(`validate-all`, `continuous-attestation`, the hard gate) re-checks authored
requirements against current code and flags any that no longer hold, scoped by
author-written path patterns in the gate policy. Behavior not captured as a
requirement is invisible to it. To protect existing behavior, characterize it as
requirements first.

### Architectural and integration design

The layer does not analyze a codebase to decide where a feature belongs or how
it should integrate. `allowed_paths` is an input you provide, not an output it
derives. Integration design is a human, architect, or planner responsibility;
the tool enforces the constraints you set and verifies the result.

### General logic and scientific validation

Spec-tier attestation checks that a *supported claim shape* — one of
`authorization_precondition`, `state_precondition`, `state_postcondition`,
`numeric_invariant`, `event_state_correspondence` — is encodable and satisfiable
under its declared assumptions, in the adapter's approved vocabulary. This is a
consistency and satisfiability check of a software-requirement-shaped claim, not
a general theorem prover, and not empirical or scientific validation of an
arbitrary hypothesis. Claims outside the supported shapes are reported as
unsupported rather than silently accepted.

## FAQ

**Does it attest a set of requirements as one composite?**
No. Independent per-requirement verdicts plus a status roll-up. There is no
composite claim.

**Will it catch a contradiction between requirement A and requirement Z?**
No. Each is checked alone; both can pass while mutually inconsistent. Within a
single requirement, conflicting conditions are caught.

**Does it decompose a requirement into implementation steps?**
No. Author atomic requirements upstream; the tool enforces atomicity and
bundles, it does not subdivide.

**Does it write code or call an agent?**
No. It emits work orders and verdicts; an external agent or human does the
coding.

**Will it tell me if a change breaks my (brownfield) app?**
Only for behaviors you have captured as requirements and mapped to the changed
paths. Un-attested behavior is not covered.

**Will it tell me where or how a feature should fit in a legacy app?**
No. That is design work done outside the tool; the tool enforces the
`allowed_paths` you choose.

**Can it validate a scientific hypothesis with no app?**
Only as a consistency and satisfiability check of a claim that fits a supported
shape and vocabulary, not scientific validation or general theorem proving.

## Related Notes

- `future-adapter-routing.md` — adapter-strategy non-goals (no trust from file
  extension alone, no agent or LLM output as evidence, no silent generic
  success, no in-place mutation of reviewed packages).
- `build-plan.md` — cross-system requirements out of scope.
- Per-phase docs (`phase-7-openapi-adapter.md`, `phase-10-command-test-runner-adapter.md`, and siblings)
  — adapter- and phase-specific scope notes.
