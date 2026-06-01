# ADR 0029: System Spec Registry

## Status

Proposed

## Context

The vision requires checking a new requirement `R` against the existing verified
system spec `S`. So far, requirement packages are checked mostly in isolation,
and TLA model evidence is tied to individual reviewed models rather than a
registry of the system's current specs.

Before `S ∧ R` checking can exist, `S` must be addressable, reviewed, versioned,
hash-bound, and freshness-aware.

## Decision

Introduce a system spec registry artifact.

The registry maps module ids to spec entries with:

- spec id;
- module ids;
- formalism;
- project-root-relative path;
- version;
- review status;
- freshness status;
- optional recorded hash;
- metadata.

Validation computes current hashes and reports missing or stale specs. Impact
analysis can query the registry for specs relevant to affected modules.

Specula extraction is out of scope for this ADR. Extracted specs may become
draft registry entries in a later phase, but they are not reviewed `S` until a
human accepts them.

## Consequences

The project gains a stable representation of system spec `S`, which unblocks
future `S ∧ R` composition.

The tradeoff is manual registry maintenance at first. That is acceptable because
Phase 25 establishes the trust anchor before automation is introduced.
