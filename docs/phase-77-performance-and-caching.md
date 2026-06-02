# Phase 77 - Performance And Caching

## Status

Implemented as a schema-backed cache key and lookup layer.

## Purpose

Make expensive verification stages reusable without weakening evidence
semantics. Repeated parsing, impact analysis, lowering, backend execution, trace
extraction, and proof-object construction should be reusable only when all
meaningful inputs still match.

## Scope

The phase defines cache keys and records. It does not decide when a caller
should trust a hit; consuming workflows remain responsible for checking policy,
artifact retention, producer validation, and evidence-level requirements.

## Data Contracts

- `VerificationCacheKey` records stage, input hashes, tool versions, and an
  optional policy hash.
- `VerificationCacheRecord` records cache key hash, artifact hash, stage, hit
  count, and metadata.
- `VerificationCacheIndex` stores unique cache records.
- `VerificationCacheLookup` returns explicit `hit` or `miss`.

The implemented schemas are:

- `schemas/verification-cache-key.schema.json`
- `schemas/verification-cache-index.schema.json`
- `schemas/verification-cache-lookup.schema.json`

## API

Implementation module: `nlreq.verification_cache`.

Core functions:

- `build_verification_cache_key(...)` canonicalizes key material.
- `cache_key_hash(...)` computes the stable key hash.
- `lookup_cache(...)` returns hit or miss.
- `record_cache_artifact(...)` records a retained artifact hash or increments
  the hit count for an existing key.

## Invalidation Rules

- Changed input hashes produce a different key.
- Changed tool versions produce a different key.
- Changed policy hashes produce a different key.
- Cache records point to artifacts by hash; artifact lookup is still required to
  prove the retained artifact exists and has not changed.
- Cache hits must be disclosed in reports and cannot upgrade an evidence label.

## Verification

`tests/test_milestone_group6.py` verifies hits for identical keys and misses
for changed tool versions or policy hashes.

## Exit Criteria

- Repeated gate runs can reuse safe artifacts through hash-keyed records.
- Cache reuse is invalidated by changed inputs, tool versions, or policy.
- Cache hits are reportable through cache records.
- Cache reuse does not change the assurance level of the underlying evidence.
