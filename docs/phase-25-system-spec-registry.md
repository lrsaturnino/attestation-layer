# Phase 25 System Spec Registry

Phase 25 introduces the existing system specification `S` as a first-class
artifact.

This phase starts with manual, reviewed, versioned specs. Spec extraction and
coverage automation belong to later phases.

## Purpose

The phase lets the Attestation Layer say:

```text
These implementation modules are bound to reviewed system specs, with spec
versions, hashes, formalism, freshness metadata, and stale/missing status made
explicit.
```

It does not say:

```text
The new requirement R has been checked against S.
Spec coverage is complete.
Specula extraction is implemented.
The spec matches current code traces.
```

## Registry Shape

The first registry binds module ids to system specs:

```json
{
  "schema_version": "0.1",
  "specs": [
    {
      "spec_id": "spec:auth",
      "module_ids": ["auth"],
      "formalism": "tla",
      "path": "specs/Auth.tla",
      "version": "1",
      "review_status": "reviewed",
      "freshness": "fresh"
    }
  ]
}
```

Spec files are project-root-relative and hash-addressed at validation time.

## Implementation Scope

Phase 25 implementation should include:

- system spec registry models and JSON schema;
- path validation;
- spec hash computation;
- module lookup for impact-analysis output;
- stale and missing spec reporting;
- CLI validation/reporting command;
- tests for fresh, stale, and missing specs.

## Evidence Semantics

Registry validation is not `S ∧ R` checking.

Fresh reviewed specs are eligible inputs for later system-consistency checks.
Missing, stale, draft, rejected, or unreviewed specs are non-approving states for
future phases.

## Success Criterion

Phase 25 succeeds when:

- modules bind to formal specs through a registry;
- spec hashes and versions are recorded;
- requirements can identify relevant `S` entries through impact output;
- stale or missing `S` is explicit;
- and no system-consistency proof is claimed.

## Boundary

This phase is not `S ∧ R`, Specula extraction, spec coverage gating, trace
alignment, or proof closure.
