# ADR 0073: Spec Freshness Lockfile And Hash-Based Drift Invariant

## Status

Proposed

## Context

Registry freshness is not enough unless it can be reproduced from current files.

## Decision

Add a spec freshness lockfile containing source hashes, spec hashes, dependency
module IDs, and manifest-entry hashes.

## Consequences

Changed source or spec content invalidates freshness even when registry labels
remain stale.

## Validation

Tests cover source changes blocking lockfile validation.
