# Phase 37 Spec Drift CI

Phase 37 keeps reviewed specs from silently diverging from source code. A
code-to-spec manifest records source hashes and dependency edges; CI can compare
current source hashes against the manifest, report drift, and mark affected specs
stale.

## Purpose

The phase lets the Attestation Layer say:

```text
This code change affects these spec-covered modules, these specs are stale, and
these refresh actions are required before proof closure can continue.
```

It does not say:

```text
The refreshed spec is correct.
Every semantic dependency was inferred automatically.
Stale specs can still satisfy closure.
```

## Implementation Scope

Phase 37 implementation includes:

- code-to-spec manifest model and schema;
- recorded source hashes per module;
- dependency-module edges for drift propagation;
- spec drift report model and schema;
- missing-source, direct-stale, and dependency-stale statuses;
- required refresh actions;
- helper to mark affected specs stale in the system spec registry;
- CLI command for `spec-drift`;
- tests for fresh, changed, dependency-propagated, missing-source, and CLI
  workflows.

## Evidence Semantics

Spec drift is a blocking freshness gate. Any stale or missing-source status
blocks the report. Marked stale specs cannot satisfy coverage or proof closure
until reviewed and refreshed.

The manifest is deterministic. It does not infer all semantic dependencies; it
records the dependencies that CI policy knows how to enforce.

## Success Criterion

Phase 37 succeeds when:

- code changes deterministically stale affected spec entries;
- dependency drift propagates to dependent modules;
- stale specs block closure through existing coverage/freshness gates;
- CI output names modules, specs, changed paths, and refresh actions;
- the report is schema-backed and CLI-addressable.

## Boundary

This phase is not full semantic impact analysis. Phase 38 broadens targeting
with call graph and semantic disagreement context.
