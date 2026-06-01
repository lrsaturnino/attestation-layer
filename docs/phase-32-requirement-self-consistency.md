# Phase 32 Requirement Self-Consistency

Phase 32 checks a formalized requirement `R` before composing it with reviewed
system specs `S`. The goal is to refuse contradictions, unsupported fragments,
timeouts, and backend counterexamples while the failure is still local to the
requirement.

## Purpose

The phase lets the Attestation Layer say:

```text
R was checked by itself before S-and-R composition, and the result was valid,
contradictory, unsupported, timed out, or failed as a tool error.
```

It does not say:

```text
R is compatible with the existing system.
R is grounded against runtime traces.
R has an inductive proof.
```

## Implementation Scope

Phase 32 implementation includes:

- requirement self-consistency result model and schema;
- deterministic precheck for impossible comparisons and directly opposite
  fragments inside conjunctions;
- formal backend execution over `R` alone;
- structured mapping for valid, contradiction, unsupported, timeout, and
  tool-error outcomes;
- preservation of backend counterexample and unsupported-node details;
- CLI command for `requirement-self-consistency`;
- tests for valid runs, deterministic contradictions, backend
  counterexamples, unsupported fragments, timeouts, and CLI output.

## Evidence Semantics

Self-consistency is a gate before system composition. A valid bounded backend
run may carry `BOUNDED_CHECKED` in the self-consistency result. Contradiction,
unsupported, timeout, and tool-error outcomes never approve.

The deterministic precheck is intentionally narrow. It catches obvious
contradictions before invoking the backend, but richer contradiction discovery
belongs to solver-backed formal execution.

## Success Criterion

Phase 32 succeeds when:

- contradictory requirement fixtures fail before system composition;
- unsupported fragments name the exact IR node;
- backend counterexamples are reported as contradictions of `R` checked alone;
- timeouts record their budget through the backend/runner metadata and never
  approve;
- the result is schema-backed and CLI-addressable.

## Boundary

This phase is not solver-backed `S and R`, trace replay, or translator
agreement. It only answers whether `R` is acceptable to carry forward into those
later checks.
