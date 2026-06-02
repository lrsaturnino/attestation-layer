# ADR 0086: Verification Cache, Invalidation, And Evidence Disclosure Policy

## Status

Accepted

## Context

Formal backends, trace extraction, source impact, lowering, and proof closure can
be expensive enough to slow developer workflows. Caching is necessary, but cache
reuse must not create stale evidence or upgrade assurance claims.

## Decision

Introduce `nlreq.verification_cache` with schema-backed cache keys, records, and
lookups.

A cache key includes:

- verification stage;
- input hashes;
- tool versions;
- optional policy hash.

Cache records point to retained artifact hashes and disclose hit counts. Lookup
returns explicit `hit` or `miss`.

## Rationale

Tool versions and policy hashes are part of the semantic input to verification.
Including them in the key prevents reuse across changed checkers, changed
normalizers, or changed gate requirements.

## Consequences

Positive:

- Repeated runs can reuse artifacts when inputs are unchanged.
- Changed inputs, tool versions, or policy produce misses.
- Cache reuse is visible and auditable.

Negative:

- The cache layer does not prove retained artifact availability; callers still
  need artifact-store lookup.
- Overly broad input hashes can reduce cache hit rates.

## Alternatives Considered

- Key only by requirement id. Rejected because it would allow stale reuse after
  code, spec, tool, or policy changes.
- Treat cache hits as stronger evidence. Rejected because caching changes
  performance, not proof strength.

## Validation

`tests/test_milestone_group6.py` covers cache hits for identical keys and misses
for changed tool versions or policy hashes.
