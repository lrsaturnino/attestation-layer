# ADR 0155: Performance, Caching, And Parallel Dispatch

## Status

Accepted

## Context

Real evidence paths are expensive enough that CI needs safe cache reuse and
parallel dispatch. Unsafe reuse would be worse than no cache because it could
hide changed inputs.

## Decision

Use v2 cache policy and dispatch artifacts. Cache keys include stage, input
hashes, tool versions, and policy hash. The dispatch plan reports cache hits,
misses, non-cacheable work, run slots, estimated runtime, CI budget, and
blocking findings.

## Consequences

Unchanged evidence can be reused when its cache key matches exactly. Changed
inputs, tool versions, or policy produce a different key and invalidate the
cache. The tradeoff is that every cacheable task must provide complete input
hashes.

## Validation

Group 14 tests verify cache hits, changed-input misses, and runtime budget
blocking.
