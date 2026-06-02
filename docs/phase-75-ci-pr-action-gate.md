# Phase 75 - CI And PR Action Gate

## Status

Implemented.

## Purpose

Make closure decisions usable in ordinary engineering workflows. The official
gate output must be machine-readable, suitable for required checks, and
renderable as concise PR feedback.

## Scope

The phase adds a CI/PR report layer over the end-to-end requirement gate. It
supports report-only adoption, soft-gate execution, and hard-gate blocking for
repositories that are ready to enforce closure before downstream actions.

## Data Contracts

`CiPrGateReport` records:

- mode: `report_only`, `soft_gate`, or `hard_gate`;
- result: `reported`, `passed`, or `blocked`;
- requirement id, closure decision, and downstream-action permission;
- retained artifact hashes;
- next actions derived from gate blockers;
- input hashes for the source end-to-end report and supplied artifact records.

The implemented schema is `schemas/ci-pr-gate-report.schema.json`.

## API And CLI

Implementation module: `nlreq.ci_pr_gate`.

Core functions:

- `build_ci_pr_gate_report(...)` converts an end-to-end gate report into CI
  policy output.
- `ci_pr_gate_markdown(...)` renders PR-safe Markdown from the JSON report.

CLI:

- `nlreq ci-pr-gate --gate-report <path> --mode report_only`
- `nlreq ci-pr-gate --gate-report <path> --mode hard_gate`
- optional artifact records can be supplied so uploaded artifacts remain
  hash-linked in the CI report.

## Enforcement Rules

- Report-only mode never blocks by itself.
- Hard-gate mode blocks when the underlying gate does not allow the downstream
  action.
- Markdown is never the source of truth; the JSON report is authoritative.
- Blocker messages become next actions for reviewer and implementer feedback.
- Artifact hashes are surfaced so CI uploads can be tied back to retained
  evidence.

## Verification

`tests/test_milestone_group6.py` verifies report-only behavior, hard-gate
blocking, next-action propagation, and Markdown rendering.

## Exit Criteria

- A repository can run the gate in report-only mode.
- A repository can enable hard-gate mode for selected requirement classes.
- PR feedback includes accepted/refused/unknown summaries and next actions.
- Artifacts are hash-linked in the machine-readable report.
