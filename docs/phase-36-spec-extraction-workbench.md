# Phase 36 Spec Extraction Workbench

Phase 36 adds a brownfield workbench for modules that do not yet have fresh
reviewed formal specs. The workbench emits candidate specs with provenance and
trace-grounding context, but the candidates remain draft-only until explicitly
reviewed and hash-promoted.

## Purpose

The phase lets the Attestation Layer say:

```text
This affected module lacks usable spec coverage, so here is a draft candidate
spec with extraction provenance, known gaps, and trace-grounding context.
```

It does not say:

```text
The extracted candidate is reviewed.
The candidate can satisfy coverage.
The candidate closes proof.
```

## Implementation Scope

Phase 36 implementation includes:

- spec extraction workbench report model and schema;
- draft candidate spec model with content hash, path, formalism, gaps, and
  provenance;
- affected-module selection from impact plus system spec registry freshness;
- optional code presentation and trace replay provenance hashes;
- draft `SystemSpecEntry` conversion that remains unreviewed;
- explicit hash-checked promotion helper for reviewed specs;
- CLI command for `spec-extract`;
- tests that draft candidates cannot satisfy coverage.

## Evidence Semantics

Extracted specs are `draft` with `unknown` freshness. They cannot satisfy spec
coverage, proof closure, or freshness gates. Promotion to reviewed/fresh spec
entry requires an explicit matching content hash.

Trace grounding in this phase is context for reviewers. It does not make a draft
spec trusted.

## Success Criterion

Phase 36 succeeds when:

- under-specified affected modules produce candidate specs;
- candidates include provenance and known gaps;
- trace-grounding report hashes are recorded when supplied;
- draft candidates remain blocked by coverage;
- reviewed promotion is explicit and hash-based;
- the report is schema-backed and CLI-addressable.

## Boundary

This phase does not infer complete formal semantics from code. It creates
review-ready artifacts and preserves the trust boundary between extracted drafts
and reviewed specs.
