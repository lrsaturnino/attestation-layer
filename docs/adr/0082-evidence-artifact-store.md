# ADR 0082: Evidence Artifact Store, Retention, And Replay Bundle Format

## Status

Accepted

## Context

Closure reports reference backend logs, normalized reports, benchmark inputs, and
other evidence artifacts. If those files are transient, downstream users cannot
replay a decision or audit whether a reported hash still resolves.

The conclusion roadmap requires evidence integrity before CI adoption and public
benchmark claims. Retention must be deterministic, local-first, and simple
enough to use without external infrastructure.

## Decision

Introduce a local filesystem artifact store implemented by
`nlreq.artifact_store`.

Artifacts are stored by SHA-256 content hash under a deterministic object path.
The manifest records logical name, media type, store path, size, raw/normalized
role flags, retention state, and metadata. Lookup verifies both manifest
membership and current file hash.

The store exposes:

- `ArtifactStoreManifest`
- `ArtifactLookupResult`
- `ReplayBundleManifest`
- `nlreq artifact-put`
- `nlreq artifact-get`

Replay bundles copy resolvable retained records while preserving content hashes.

## Rationale

Content addressing gives reports a stable reference independent of filenames and
temporary directories. A local store keeps the first implementation dependency
free while leaving room for object-store or remote-retention backends with the
same manifest semantics.

## Consequences

Positive:

- Missing artifacts and hash mismatches become explicit integrity failures.
- Raw and normalized artifacts can be retained together.
- Benchmark runs and release reports can export replay bundles.

Negative:

- The store does not decide whether an artifact is trustworthy.
- Garbage collection policy remains conservative until retention windows are
  added by later release hardening.

## Alternatives Considered

- Embed all evidence inline in closure reports. Rejected because reports would
  become large and would still not solve raw artifact retention.
- Use a remote object store first. Rejected because it would add infrastructure
  before the local retention contract is stable.

## Validation

`tests/test_milestone_group6.py` covers retained artifact lookup, missing hashes,
raw role flags, and replay bundle export.
