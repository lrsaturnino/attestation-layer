# ADR 0120: CI Adoption And Gate Modes

## Status

Accepted

## Context

Adopters need report-only rollout, advisory soft gates, and blocking hard
gates. The release certification process also needs to ensure that the hard
gate is based on machine-readable output, not PR Markdown.

## Decision

Add `CiAdoptionPolicy` and `ExtendedCiPrGateReport`.

The supported modes are:

- `report_only`, with no enforcement;
- `soft_gate`, with advisory enforcement;
- `hard_gate`, with blocking enforcement.

The JSON report is authoritative. Markdown is generated from JSON and is only a
human presentation surface.

## Rationale

Rollout and release certification have different needs. A single report shape
with explicit mode and enforcement fields allows both without changing proof
objects or gate semantics.

## Consequences

Positive:

- Teams can adopt gradually.
- Release certification can require hard-gate mode.
- PR Markdown includes stable JSON hashes for audit.

Negative:

- Soft-gate output can be blocked while still advisory, so host CI policy must
  interpret the enforcement field correctly.

## Validation

`tests/test_milestone_group9.py` verifies report-only behavior, hard-gate
blocking, stable JSON hashes, and Markdown rendering.
