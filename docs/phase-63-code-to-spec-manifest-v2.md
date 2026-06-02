# Phase 63 - Code-To-Spec Manifest v2

## Status

Implemented through the code-spec manifest and freshness lock integration.

## Purpose

Map source modules to reviewed specs, dependencies, and source hashes in one
artifact.

## Implementation

- Existing `nlreq.spec_drift.CodeSpecManifest`
- `schemas/code-spec-manifest.schema.json`
- `nlreq spec-drift`
- Phase 64 lockfile integration

The manifest records module IDs, source paths, spec IDs, dependency modules, and
recorded source hashes. Drift propagates across dependency edges.

## Exit Criteria

- Changed source blocks freshness.
- Missing source is explicit.
- Dependency drift propagates to dependent modules.
