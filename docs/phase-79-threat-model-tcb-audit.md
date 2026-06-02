# Phase 79 - Threat Model And TCB Audit

## Status

Implemented.

## Purpose

Name the trusted computing base for conclusion-release claims and make
adversarial evidence scenarios visible before certification.

This phase is not a penetration test and does not prove the TCB is correct. It
creates the release artifact that says which components are trusted, what each
component is trusted to do, how failures affect proof closure, and which threat
classes must appear in benchmark coverage.

## Scope

The threat model covers:

- controlled parser and IR validator;
- translator workbench and human review approval;
- formal backend wrappers;
- source adapters and trace producers;
- evidence artifact store and producer registry;
- CI/action gate enforcement.

The required threat classes for the conclusion release are spoofing, tampering,
replay, prompt injection, stale specs, forged evidence, and malicious adapters.
Every threat class must have at least one benchmark-required scenario.

## Data Contracts

Implementation module: `nlreq.threat_model`.

Primary schema:

- `schemas/threat-model-report.schema.json`

Primary model:

- `ThreatModelReport`

Important fields:

- `tcb`: trusted components, category, assumption, and failure impact.
- `scenarios`: threat scenarios with affected TCB components, mitigation,
  residual risk, and benchmark-required flag.
- `security_checklist`: release-review checklist items.
- `release_claims`: boundaries on what certification may claim.
- `audit_findings`: deterministic completeness findings.

## API And CLI

Core functions:

- `build_default_threat_model()`
- `threat_model_release_findings(report)`

CLI:

```bash
uv run nlreq threat-model --out /tmp/threat-model.json
```

## Invariants

- A complete release threat model must cover every required TCB category.
- Scenario `affected_components` values must refer to declared TCB component
  ids.
- Every required threat class must be present.
- Every required threat class must have benchmark-required coverage.
- Empty security checklists and empty release claim boundaries are release
  blockers.
- Threat model completion does not upgrade evidence labels or prove semantic
  correctness.

## Verification

`tests/test_milestone_group7.py` verifies that the default threat model has a
complete TCB, covers required threat classes, marks benchmark-required
scenarios, and reports deterministic findings when a required TCB category is
removed.

## Exit Criteria

- High-assurance claims can point to explicit TCB assumptions.
- All required adversarial classes are named and benchmark-required.
- Residual risks and claim boundaries are present in machine-readable output.
- Conclusion certification fails when threat-model completeness fails.
