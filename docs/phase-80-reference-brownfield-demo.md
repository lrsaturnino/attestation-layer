# Phase 80 - Reference Brownfield Demo

## Status

Implemented as a reproducibility manifest contract.

## Purpose

Provide the machine-readable shape for a reproducible brownfield demo with both
accepted and refused requirements.

## Implementation

- `nlreq.reference_demo`
- `nlreq reference-demo-check`
- `schemas/reference-demo-manifest.schema.json`
- `schemas/reference-demo-report.schema.json`

The manifest lists source root, requirements, formal specs, trace artifacts,
commands, and reproducibility notes. Validation checks artifact presence.

## Exit Criteria

- Demo manifests must include accepted and refused requirements.
- Missing artifacts are explicit blockers.
- Demo report is suitable for conclusion certification.
