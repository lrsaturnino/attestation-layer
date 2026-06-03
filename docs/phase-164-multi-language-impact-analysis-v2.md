# Phase 164 - Multi-Language Impact Analysis v2

## Status

Implemented.

## Purpose

Close the milestone 17 gap for affected system area discovery.

## Implementation

Primary module:

- `src/nlreq/real_evidence.py`

Inputs:

- retained evidence artifact hashes;
- producer, review, replay, and signing metadata;
- accepted ADR status for the phase decision.

Outputs:

- a `RealEvidencePhaseReport` with criteria, blockers, limitations, and input hashes;
- milestone aggregation through `RealEvidenceMilestoneReport`;
- final target alignment through `ClaudeConvoGapAssessment`.

Primary artifacts:

- `RealEvidencePhasePlan`
- `RealEvidenceArtifactRef`
- `RealEvidencePhaseReport`

Schemas:

- `schemas/real-evidence-phase-plan.schema.json`
- `schemas/real-evidence-phase-report.schema.json`

## Required Evidence

- `impact_report_v2`
- `symbol_resolution_report`
- `call_graph_report`
- `impact_disagreement_report`

## Contract

The phase report passes only when every required artifact type is supplied, accepted, reviewed, replayable, and marked as real evidence. The report records the required ADR, artifact hashes, blockers, and scoped limitations. It does not treat fixture-only or scaffold evidence as release evidence.

## Exit Criteria

- all required evidence artifact types are present;
- all required artifacts have accepted status;
- all required artifacts are reviewed and replayable;
- no required artifact is marked as scaffold or fixture-only evidence;
- the corresponding ADR is accepted;
- the phase result is `passed` and can be aggregated into its milestone.

## Blocking Behavior

- missing required artifact
- scaffold or fixture-only evidence
- blocked evidence artifact
- unreviewed release-critical evidence

## Limitations

- This phase report certifies retained evidence inputs, not the correctness of arbitrary natural language or arbitrary programs.
- Bounded or trace evidence remains scoped to its declared budgets, traces, producers, and adapters.

## Verification

`tests/test_milestone_groups_15_to_20.py` verifies phase registry coverage, positive closure with required artifacts, and blocking behavior for missing or scaffold evidence.
