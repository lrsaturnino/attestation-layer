# Phase 111 CI Adoption Modes

Phase 111 hardens how CI and PR workflows consume the extended gate.

## Purpose

Engineering teams need a path from report-only adoption to hard enforcement.
The CI contract must keep JSON authoritative while still producing useful PR
Markdown for humans.

## Contracts

Implementation:

- `CiAdoptionPolicy`
- `ExtendedCiPrGateReport`
- `build_ci_adoption_report`
- `extended_ci_pr_gate_markdown`
- CLI command `nlreq ci-adoption`

Schemas:

- `schemas/ci-adoption-policy.schema.json`
- `schemas/extended-ci-pr-gate-report.schema.json`

## Modes

`report_only` records the gate decision and never blocks. It is for discovery,
initial rollout, and benchmark collection.

`soft_gate` reports blocked checks as advisory. The machine-readable result can
be `blocked`, but enforcement is `advisory`.

`hard_gate` is the release certification mode. A blocked check means the CI
result is blocked and downstream action must not proceed.

## Required Checks

The default policy requires:

- an extended gate artifact;
- a stable JSON hash;
- PR Markdown rendering;
- a machine-readable result.

Waivers can be represented by ID, but waiver policy does not make the gate pass
unless the configured policy allows waivers.

## Exit Criteria

- Report-only, soft-gate, and hard-gate modes produce stable JSON.
- PR Markdown includes mode, result, enforcement, decision, downstream action,
  and stable JSON hash.
- Hard-gate mode blocks when the extended gate is not accepted.
- Tests cover report-only and hard-gate behavior.
