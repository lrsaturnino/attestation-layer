# ADR 0084: CI/PR Action Gate, Report-Only Adoption, And Hard-Gate Policy

## Status

Accepted

## Context

The closure gate must integrate with normal PR workflows. A developer needs a
concise status and next actions, while CI needs a stable machine-readable result
for required checks and artifact uploads.

## Decision

Add `nlreq.ci_pr_gate` as a report layer over the end-to-end requirement gate.
It emits `CiPrGateReport` JSON and a derived Markdown renderer.

Supported modes:

- `report_only`: always reports and never blocks by itself;
- `soft_gate`: records pass/block semantics without mandatory enforcement;
- `hard_gate`: blocks when the underlying gate does not allow the downstream
  action.

The JSON report is authoritative. Markdown is only a presentation layer.

## Rationale

Separating the CI/PR report from the proof pipeline keeps workflow-specific
concerns out of the proof object. It also lets teams adopt the gate in
report-only mode before enforcing hard gates.

## Consequences

Positive:

- Repositories can adopt closure reporting without immediate merge blocking.
- Hard-gate mode has an explicit machine-readable block condition.
- PR comments can include next actions without becoming the source of truth.
- Retained artifact hashes can be surfaced for CI upload and audit.

Negative:

- The CI/PR layer depends on upstream gate report quality.
- Markdown renderings must be kept in sync with JSON fields.

## Alternatives Considered

- Make the end-to-end gate report directly serve as the CI check. Rejected
  because workflow mode, PR Markdown, and artifact-upload details are adoption
  concerns.
- Use Markdown-only comments. Rejected because comments are hard to audit and
  unsuitable as required-check inputs.

## Validation

`tests/test_milestone_group6.py` covers report-only behavior, hard-gate
blocking, next-action propagation, and Markdown rendering.
