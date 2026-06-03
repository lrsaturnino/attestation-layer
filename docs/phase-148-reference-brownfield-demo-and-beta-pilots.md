# Phase 148 - Reference Brownfield Demo And Beta Pilots

## Status

Implemented.

## Purpose

Prove the system in a credible workflow by combining a replayable reference
brownfield demo with beta pilot findings.

## Implementation

Primary module:

- `src/nlreq/reference_demo.py`

Primary artifacts:

- `BetaPilotFinding`
- `BetaPilotReport`
- `ReferenceBrownfieldPilotReport`
- existing `ExtendedReferenceDemoReport`

Schemas:

- `schemas/beta-pilot-report.schema.json`
- `schemas/reference-brownfield-pilot-report.schema.json`
- `schemas/extended-reference-demo-report.schema.json`

## Contract

The brownfield pilot report accepts only when:

- the extended reference demo is reproducible;
- accepted and refused requirements have gate reports;
- replay bundle hashes are present through the extended demo report;
- at least one beta pilot report is retained;
- each pilot exercised at least one requirement;
- pilot result is passed;
- blocker-severity findings are mitigated.

All pilot findings are retained as release findings even when they do not block.

## Failure Behavior

- Non-reproducible demo blocks release.
- Missing pilot reports block release.
- Pilot result `blocked` blocks release.
- Pilot without exercised requirements blocks release.
- Unmitigated blocker finding blocks release.

## Verification

`tests/test_milestone_group14.py` verifies accepted beta pilot findings and
blocking behavior for an unmitigated pilot blocker.
