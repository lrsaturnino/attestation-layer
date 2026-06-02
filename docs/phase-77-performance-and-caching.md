# Phase 77 - Performance And Caching

## Status

Implemented.

## Purpose

Represent safe verification cache keys and cache records without weakening
evidence semantics.

## Implementation

- `nlreq.verification_cache`
- `schemas/verification-cache-key.schema.json`
- `schemas/verification-cache-index.schema.json`
- `schemas/verification-cache-lookup.schema.json`

Cache keys include stage, input hashes, tool versions, and optional policy hash.
Records store artifact hash and hit count. Cache hits do not upgrade evidence
labels.

## Exit Criteria

- Changed inputs or tool versions produce different keys.
- Cache lookup returns hit or miss explicitly.
- Cache reuse is reportable through records.
