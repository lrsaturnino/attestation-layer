# Phase 73 - Evidence Artifact Store

## Status

Implemented.

## Purpose

Make evidence replayable after the CLI process exits. Closure reports and
benchmark outputs must not depend on temporary files that disappear after a
single run.

## Scope

The phase defines a local filesystem artifact store. It retains raw backend
logs, normalized reports, benchmark inputs, and any other evidence artifact by
content hash. The store is intentionally simple: it is a deterministic layout
and manifest API that future remote or object-store implementations can mirror.

## Data Contracts

- `ArtifactRecord` records the artifact hash, logical name, media type,
  store-root-relative object path, size, raw/normalized role flags, retention
  state, and string metadata.
- `ArtifactStoreManifest` records the store id and unique artifact records.
- `ArtifactLookupResult` distinguishes `found`, `missing`, and
  `hash_mismatch`.
- `ReplayBundleManifest` records exported records for replay or benchmark
  reproduction.

The implemented schemas are:

- `schemas/artifact-store-manifest.schema.json`
- `schemas/artifact-lookup-result.schema.json`
- `schemas/replay-bundle-manifest.schema.json`

## API And CLI

Implementation module: `nlreq.artifact_store`.

Core functions:

- `put_artifact(...)` stores a source file under `objects/<prefix>/<digest>`.
- `lookup_artifact(...)` verifies manifest membership and current file hash.
- `export_replay_bundle(...)` copies all resolvable retained records into a
  replay bundle without changing hashes.

CLI:

- `nlreq artifact-put <file> --store-root <dir> --logical-name <name>`
- `nlreq artifact-get --store-root <dir> --manifest <manifest> --hash <hash>`

## Integrity Rules

- Artifact paths are store-root-relative and cannot be absolute or contain
  `..`.
- Manifest records must have unique hashes.
- Lookup fails if a hash is absent from the manifest.
- Lookup fails distinctly if the stored file exists but no longer matches the
  manifest hash.
- Export skips unresolved artifacts rather than pretending the bundle is
  complete.

## Evidence Semantics

The store makes artifacts resolvable; it does not make an artifact trustworthy
by itself. Trust comes from producer validation, signature verification, and the
proof closure policy that consumes the retained artifact hash.

## Verification

`tests/test_milestone_group6.py` verifies retained lookup, missing hash
behavior, raw-artifact flags, and replay bundle export.

## Exit Criteria

- Final reports can resolve every retained artifact hash through the store.
- Missing artifacts and hash mismatches are first-class integrity failures.
- Raw and normalized artifact roles are recorded.
- Benchmark runs can copy retained records into replay bundles.
