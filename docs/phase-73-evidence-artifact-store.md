# Phase 73 - Evidence Artifact Store

## Status

Implemented.

## Purpose

Retain evidence artifacts so proof reports remain replayable after the CLI
process exits.

## Implementation

- `nlreq.artifact_store`
- `nlreq artifact-put`
- `nlreq artifact-get`
- `schemas/artifact-store-manifest.schema.json`
- `schemas/artifact-lookup-result.schema.json`
- `schemas/replay-bundle-manifest.schema.json`

Artifacts are stored by SHA-256 content hash under a deterministic object path.
Lookup validates both manifest membership and current file hash.

## Exit Criteria

- Missing artifacts are first-class lookup failures.
- Hash mismatches are distinct from missing files.
- Raw and normalized artifact roles are recorded on each artifact record.
