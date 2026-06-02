# ADR 0119: End-To-End Requirement Gate Contract

## Status

Accepted

## Context

The first conclusion release has an end-to-end gate report, but milestone group
9 needs a stricter release contract. A release gate must name every stage needed
for the conclusion claim and must fail closed when required release evidence is
missing.

## Decision

Add `ExtendedEndToEndRequirementGateReport` as a release/adoption layer over the
existing `EndToEndRequirementGateReport`.

The extended gate requires stages for controlled intake, semantic translation,
formal claim lowering, requirement self-consistency, `S and R` composition,
spec freshness, trace validation, adapter evidence, proof closure, and release
action gating.

Missing required stages are represented as `missing`, produce stable
`NLR-EXT-GATE-*` refusal codes, and block downstream action.

## Rationale

The existing gate is an operational pipeline report. The extended gate is a
release contract. Keeping those separate preserves compatibility while making
the release bar explicit.

## Consequences

Positive:

- Release evidence cannot pass on artifact presence alone.
- Missing intake, freshness, trace, or adapter evidence is visible.
- CI and certification can consume one stable gate shape.

Negative:

- Release consumers must provide stage status overrides for evidence not yet
  present in the base gate report.

## Validation

`tests/test_milestone_group9.py` verifies accepted extended gates and
missing-stage blocking.
