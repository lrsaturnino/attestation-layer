# Phase 114 Public SDK And Docs Freeze

Phase 114 freezes public adoption documentation and schema commitments.

## Purpose

External users should not need to read internal modules to understand evidence
labels, limits, failure modes, CLI usage, schema contracts, adapter authoring,
CI modes, or SDK entry points.

## Contracts

Implementation:

- `PublicDocumentationFreezeReport`
- `build_public_documentation_freeze_report`
- CLI command `nlreq public-docs-freeze`

Schema:

- `schemas/public-documentation-freeze-report.schema.json`

## Required Topics

The default freeze requires coverage for:

- `evidence_labels`
- `limitations`
- `failure_modes`
- `cli_usage`
- `schema_guide`
- `adapter_guide`
- `ci_modes`
- `sdk_api`

The freeze report also requires schema references to be represented by frozen
schema hashes and requires at least one compatibility commitment.

## Decision Rules

The docs freeze passes only when:

- the base public documentation coverage report passed;
- every required topic is covered;
- every referenced schema has a frozen hash;
- compatibility commitments are present.

## Exit Criteria

- Public docs coverage and freeze reports are separate artifacts.
- Missing topics or schema hashes block release readiness.
- Compatibility commitments are recorded in machine-readable form.
