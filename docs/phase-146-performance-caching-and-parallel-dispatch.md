# Phase 146 - Performance, Caching, And Parallel Dispatch

## Status

Implemented.

## Purpose

Make real-evidence gates usable in CI by reusing unchanged evidence safely,
dispatching independent work in parallel, and reporting whether the reference
workflow fits the configured runtime budget.

## Implementation

Primary module:

- `src/nlreq/verification_cache.py`

Primary artifacts:

- `VerificationCachePolicyV2`
- `ParallelDispatchTask`
- `ParallelDispatchDecision`
- `ParallelDispatchPlan`
- existing `VerificationCacheKey`
- existing `VerificationCacheIndex`

Schemas:

- `schemas/verification-cache-policy-v2.schema.json`
- `schemas/parallel-dispatch-task.schema.json`
- `schemas/parallel-dispatch-plan.schema.json`

## Contract

Cache keys include:

- stage id;
- sorted input hashes;
- sorted tool versions;
- policy hash.

The v2 dispatch plan records:

- cache hit, miss, or not-cacheable decision per task;
- cache key hash per task;
- artifact hash for cache hits;
- dispatch slot for work that must run;
- estimated parallel runtime;
- configured CI runtime budget;
- budget result and findings.

Changing any input hash, tool version, stage, or policy hash changes the cache
key and forces a miss. Tasks without input hashes block because they cannot be
reused safely.

## Failure Behavior

- Missing task input hashes block dispatch.
- Estimated parallel runtime over budget blocks dispatch.
- Cache misses do not block by themselves; they schedule work.
- Non-cacheable stages do not block by themselves; they schedule work.

## Verification

`tests/test_milestone_group14.py` verifies cache reuse, changed-input
invalidation, parallel runtime accounting, and CI budget blocking.
