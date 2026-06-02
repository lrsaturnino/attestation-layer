# Phase 62 - Specula-Style Extraction Runner

## Status

Implemented as a draft candidate-spec workbench.

## Purpose

Generate candidate formal specs for affected modules without treating generated
content as reviewed truth.

## Implementation

- Existing `nlreq.spec_extraction`
- `nlreq spec-extract`
- `schemas/spec-extraction-workbench.schema.json`

Candidate specs are draft-only, hash-linked, and include gaps that require human
review. Promotion requires an approved hash.

## Exit Criteria

- Missing or stale spec coverage can produce candidate specs.
- Candidates cannot satisfy reviewed-spec gates until promoted.
- Trace and code-presentation provenance are recorded when supplied.
