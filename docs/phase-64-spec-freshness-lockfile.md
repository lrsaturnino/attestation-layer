# Phase 64 - Spec Freshness Lockfile

## Status

Implemented.

## Purpose

Make freshness reproducible from source files, spec files, manifest entries, and
registry entries.

## Implementation

- `nlreq.spec_freshness`
- `nlreq spec-freshness-lock`
- `nlreq spec-freshness-check`
- `schemas/spec-freshness-lockfile.schema.json`
- `schemas/spec-freshness-lock-report.schema.json`

The lockfile records source hashes, spec hashes, dependency modules, and
manifest-entry hashes. Validation reports stale, missing-lock, and missing-file
statuses.

## Exit Criteria

- Changed source or spec hashes block freshness.
- Lockfiles are deterministic for a given project state.
- Missing locked modules are explicit blockers.
