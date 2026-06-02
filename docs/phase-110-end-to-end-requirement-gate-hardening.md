# Phase 110 End-To-End Requirement Gate Hardening

Phase 110 makes the release gate explicit. The existing end-to-end gate already
aggregates parsing, translation agreement, self-consistency, source impact,
coverage, trace replay, system consistency, proof object, and closure gate
artifacts. The extended gate adds the stricter release view required for group
9.

## Purpose

The conclusion roadmap says downstream action is allowed only after the proof
object closes. For an extended release that decision must be auditable across
the full product path, including intake, semantic translation, formal-claim
lowering, freshness, adapter evidence, trace validation, and release action
gating.

## Contracts

Implementation:

- `ExtendedEndToEndRequirementGateReport`
- `ExtendedGateStageResult`
- `build_extended_requirement_gate_report`
- CLI command `nlreq requirement-gate-extended`

Schema:

- `schemas/extended-end-to-end-requirement-gate.schema.json`

The required release stages are:

- `controlled_intake`
- `semantic_translation`
- `formal_claim`
- `requirement_self_consistency`
- `s_and_r_composition`
- `spec_freshness`
- `trace_validation`
- `adapter_evidence`
- `proof_closure`
- `release_action_gate`

## Implementation Specification

The extended report consumes an `EndToEndRequirementGateReport` and optional
stage status overrides. Existing status fields are mapped into release stages
where possible:

- `translation_agreement` maps to `semantic_translation`;
- `requirement_self_consistency` maps directly;
- `system_consistency` maps to `s_and_r_composition`;
- `trace_alignment` plus `trace_replay` map to `trace_validation`;
- `proof_object` maps to `proof_closure`;
- `closure_gate` maps to `release_action_gate`.

Stages not present in the base report or override map become `missing`. Missing
required stages block downstream action and produce a stable refusal code of
the form `NLR-EXT-GATE-<STAGE>`.

## Decision Rules

The extended gate accepts only when:

- every required stage is `passed`;
- the base end-to-end gate allowed downstream action;
- no required stage is missing, unknown, or refused.

If any required stage is missing, unknown, timed out, unsupported, or needs
review, the decision is `unknown`. If a stage has a concrete failing status,
the decision is `refused`.

## Exit Criteria

- Extended reports include stable input hashes and the base gate hash.
- Missing adapter evidence, freshness, or intake stages block release action.
- The artifact layout version is recorded as `extended-release-v1`.
- Tests cover accepted and missing-stage outcomes.

## Tests

`tests/test_milestone_group9.py` verifies that all required stages pass for an
accepted release gate and that missing adapter evidence blocks downstream
action.
