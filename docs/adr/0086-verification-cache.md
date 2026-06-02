# ADR 0086: Verification Cache, Invalidation, And Evidence Disclosure Policy

## Status

Proposed

## Context

Formal backends and trace extraction can be expensive.

## Decision

Cache keys include stage, input hashes, tool versions, and optional policy hash.
Cache records point to retained artifact hashes and disclose hit counts.

## Consequences

Changed input or tool versions invalidate cache reuse. Cache hits do not upgrade
assurance labels.

## Validation

Cache models are schema-backed and deterministic.
