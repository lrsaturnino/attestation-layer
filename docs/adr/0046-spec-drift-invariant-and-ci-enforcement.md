# ADR 0046: Spec Drift Invariant And CI Enforcement

## Status

Proposed

## Context

Reviewed specs are only useful while they describe the code they cover. Earlier
phases can block missing, stale, or unreviewed specs, but they need a
deterministic way to decide when code changes have made a reviewed spec stale.

The roadmap requires source hashes, dependency edges, CI reporting, and closure
blocking on stale specs.

## Decision

Introduce a code-to-spec manifest and spec drift report.

Each manifest entry records:

- module id;
- source paths;
- spec ids;
- dependency module ids;
- recorded source hashes.

The drift checker compares current source hashes against the recorded hashes. It
reports:

- `fresh` when all source hashes match;
- `stale` when a source hash changed;
- `missing_source` when a mapped source path is absent.

Staleness propagates through declared dependency module ids. The report includes
changed paths, current hashes, recorded hashes, affected specs, and required
refresh actions.

A registry helper marks affected specs as `freshness=stale` so existing coverage
and proof closure gates refuse them.

## Consequences

CI can now turn code changes into deterministic spec freshness failures. The
system no longer relies on reviewers noticing that a formal spec has become
fiction.

The dependency model is explicit rather than inferred. Phase 38 can improve
impact analysis, but Phase 37 establishes the stale-spec invariant and blocking
behavior.
