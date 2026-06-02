# Phase 116 Extended Conclusion Certification

Phase 116 certifies the extended conclusion release against group 9 evidence.

## Purpose

The project can publish a conclusion claim only when release evidence proves
that the gate, CI, benchmarks, demo, public docs, TCB review, schemas, producer
evidence, and release bundle are all present and passing.

## Contracts

Implementation:

- `ExtendedConclusionCertificationReport`
- `build_extended_conclusion_certification_report`
- CLI command `nlreq extended-conclusion-certify`

Schema:

- `schemas/extended-conclusion-certification-report.schema.json`

## Certification Inputs

Required inputs:

- extended end-to-end gate report;
- extended CI hard-gate report;
- extended benchmark report;
- extended reference demo report;
- public documentation freeze report;
- extended TCB review report;
- schema freeze evidence;
- producer evidence validation;
- release bundle hash;
- signed release bundle hash unless explicitly allowed.

## Decision Rules

Certification blocks when any required criterion fails. The report keeps
blocking findings grouped by criterion and preserves evidence-level claims and
known limitations.

Release certification requires hard-gate CI mode. Report-only or soft-gate
adoption can be useful during rollout, but it cannot certify the release.

## Exit Criteria

- Complete release evidence produces `certified`.
- Missing schema freeze, producer evidence, CI hard-gate mode, or release bundle
  produces `blocked`.
- Evidence labels remain explicit: bounded checks are not inductive proofs and
  trace validation is not theorem evidence.
