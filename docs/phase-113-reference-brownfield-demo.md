# Phase 113 Reference Brownfield Demo

Phase 113 strengthens the reference demo from artifact presence checking to
extended gate and replay evidence.

## Purpose

A conclusion release needs one credible real or realistic system that exercises
the product path. The demo must include both accepted and refused requirements
so adopters can see closure and refusal behavior.

## Contracts

Implementation:

- `ExtendedReferenceDemoGateRun`
- `ExtendedReferenceDemoReport`
- `build_extended_reference_demo_report`
- CLI command `nlreq reference-demo-extended`

Schema:

- `schemas/extended-reference-demo-report.schema.json`

## Demo Requirements

The demo manifest must include:

- source root;
- controlled requirements;
- system specs;
- trace artifacts;
- reproducibility commands;
- expected accepted and refused decisions.

The extended report adds:

- one extended gate report per demo requirement;
- replay bundle hashes for every gate report;
- required pipeline stage checks;
- decision mismatch detection.

Expected refused requirements are valid when the refusal decision matches the
manifest and a replay bundle is present. Failed stages in an expected refused
case are not release blockers by themselves.

## Exit Criteria

- Accepted demo requirements pass every required extended gate stage.
- Refused demo requirements reproduce the expected refusal.
- Every demo gate report has a replay bundle hash.
- Missing gate reports, missing replay bundles, and decision mismatches block.
