# Phase 38 Source Impact Analysis

Phase 38 improves brownfield targeting before coverage, drift, and verification
run. It combines deterministic call graph expansion, runtime trace touchpoints,
and non-approving semantic suggestions with explicit disagreement reporting.

## Purpose

The phase lets the Attestation Layer say:

```text
These modules are deterministically impacted, these modules were touched by
runtime traces, and these semantic suggestions disagree with deterministic
impact.
```

It does not say:

```text
Semantic suggestions approve impact.
Trace touchpoints prove source dependencies.
All language-specific import semantics are solved.
```

## Implementation Scope

Phase 38 implementation includes:

- source impact analysis model and schema;
- bidirectional deterministic call graph expansion;
- runtime trace touchpoint extraction from trace and event metadata;
- optional semantic impact suggestions with source labels;
- disagreement records for semantic-only and trace-only modules;
- CLI command for `python-source-impact-context`;
- tests for call graph expansion, trace touchpoints, semantic disagreement, and
  CLI output.

## Evidence Semantics

Deterministic impact drives affected modules. Runtime trace touchpoints broaden
the report for review and coverage targeting. Semantic suggestions are
non-approving context only; disagreement is visible and cannot silently expand
proof closure.

## Success Criterion

Phase 38 succeeds when:

- affected modules are derived from source structure and trace touchpoints;
- deterministic and semantic disagreements are visible;
- spec coverage and later extraction can consume the richer affected-module
  list;
- the report is schema-backed and CLI-addressable.

## Boundary

This phase is not complete program slicing. It establishes a richer,
deterministic-first impact surface that later adapter-specific analysis can
strengthen.
