# ADR 0141: Code-To-Spec Coverage Manifest v2

## Status

Accepted

## Context

Coverage must distinguish reviewed formal specs from generated candidates and
partial mappings. Without that distinction, a requirement could close against a
spec that has never been reviewed or that misses dependency behavior.

## Decision

Add `CodeSpecCoverageManifestV2` and `CodeSpecCoverageGateReportV2` in
`nlreq.coverage_alignment`.

Closure is allowed only when every affected module has reviewed, full, fresh
coverage above threshold. Candidate, draft, rejected, missing, stale, partial,
unsupported, and dependency-gapped entries block closure.

## Consequences

Generated specs can be tracked in the manifest but cannot satisfy coverage.
Dependency gaps propagate to affected modules so a locally covered module does
not pass when a dependency it relies on is uncovered.

## Validation

Group 12 tests verify candidate coverage blocking and dependency propagation.
