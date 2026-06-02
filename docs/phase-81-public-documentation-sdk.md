# Phase 81 - Public Documentation And SDK

## Status

Implemented as a versioned documentation index contract.

## Purpose

Make external adoption discoverable and schema-versioned.

## Implementation

- `nlreq.public_sdk`
- `nlreq public-docs-index`
- `schemas/public-documentation-index.schema.json`

The index names getting-started, adapter SDK, formal backend SDK, and operator
guides plus example templates. It binds docs to schema references.

## Exit Criteria

- Public docs and examples have stable IDs.
- Adapter and backend authors can discover relevant schemas.
- Docs are versioned with the codebase.
