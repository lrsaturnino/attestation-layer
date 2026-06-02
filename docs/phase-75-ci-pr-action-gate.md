# Phase 75 - CI And PR Action Gate

## Status

Implemented.

## Purpose

Expose proof closure as a CI/PR control that can run report-only, soft-gate, or
hard-gate modes.

## Implementation

- `nlreq.ci_pr_gate`
- `nlreq ci-pr-gate`
- `schemas/ci-pr-gate-report.schema.json`

The report consumes an end-to-end gate report and emits machine-readable mode,
result, decision, downstream-action status, retained artifact hashes, and next
actions. Markdown rendering is derived from the JSON report.

## Exit Criteria

- Report-only mode never blocks by itself.
- Hard-gate mode blocks when downstream action is not allowed.
- PR Markdown is not the source of truth.
