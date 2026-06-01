# Phase 27 Spec Coverage And Trace Alignment

Phase 27 closes the first brownfield drift gap: affected modules must have fresh
reviewed system specs, and observed traces must be alignable with the current
requirement/spec context.

This phase introduces coverage and alignment reports. It does not implement
Specula extraction or make traces proof.

## Purpose

The phase lets the Attestation Layer say:

```text
The modules affected by a requirement have explicit spec coverage status,
freshness status is visible, and traces can be classified as aligned,
violating, or uncovered for the requirement context.
```

It does not say:

```text
Specs were automatically extracted.
The spec is proven equivalent to code.
Trace observations prove the requirement.
```

## Implementation Scope

Phase 27 implementation should include:

- spec coverage report from impact analysis and system spec registry;
- coverage threshold handling;
- stale/missing/under-reviewed spec blocking states;
- trace alignment report over normalized traces and requirement action context;
- freshness report reuse from the system spec registry;
- JSON schemas and CLI commands;
- tests for covered, under-specified, stale, aligned, violating, and uncovered
  traces.

## Evidence Semantics

Coverage and alignment reports are gating context, not proof.

Under-specified, stale, missing, violating, or uncovered states are
non-approving. Aligned traces may inform review, but they do not satisfy
`PROVEN_INDUCTIVE` or replace `S ∧ R`.

## Success Criterion

Phase 27 succeeds when:

- affected modules have coverage status;
- requirements touching under-specified modules are blocked;
- stale specs are reported;
- normalized traces are classified against requirement context;
- extraction proposals remain out of trust scope;
- and existing trace validation remains compatible.

## Boundary

This phase is not Specula extraction, full code/spec equivalence, proof closure,
or downstream action gating.
