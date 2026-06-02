# ADR 0082: Evidence Artifact Store, Retention, And Replay Bundle Format

## Status

Proposed

## Context

Proof reports reference artifacts that must remain resolvable after execution.

## Decision

Store artifacts by SHA-256 content hash and record logical name, media type,
store path, size, raw/normalized role, and metadata.

## Consequences

Reports can detect missing and hash-mismatched artifacts. Replay bundles can
copy retained records without changing their hashes.

## Validation

`artifact-put` and `artifact-get` exercise storage and lookup.
