# CI And Evidence Operator Guide

Operators wire attestation reports into delivery workflows. JSON reports are
the source of truth; Markdown comments and dashboards are derived renderings.

## Required Contracts

- `schemas/end-to-end-requirement-gate.schema.json`
- `schemas/ci-pr-gate-report.schema.json`
- `schemas/artifact-store-manifest.schema.json`
- `schemas/signed-evidence-envelope.schema.json`
- `schemas/waiver-audit-report.schema.json`
- `schemas/conclusion-certification-report.schema.json`

## Gate Modes

- `report_only` records findings but allows downstream action.
- `soft_gate` reports blocked closure without enforcing the final action.
- `hard_gate` blocks downstream action when proof closure is not closed.

## Release Operations

Before certification, retain all required artifacts, verify high-assurance
producer signatures where policy requires them, run benchmark evaluation,
validate the reference demo, run the public docs check, and freeze generated
schemas.
