# ADR 0091: Conclusion Release Criteria, Certification Process, And Public Claim Boundaries

## Status

Accepted

## Context

The conclusion roadmap needs a formal stop condition. A release cannot be
certified because a maintainer says it is ready; it must be certified by a
machine-readable report over evidence.

Earlier phases produce many useful reports, but they have different meanings:
bounded checks are not inductive proofs, traces are not theorems, signatures do
not imply semantic correctness, and adapter certification does not prove every
program behavior. The conclusion release needs to preserve these boundaries.

## Decision

Add a `ConclusionCertificationReport` built by
`nlreq.conclusion_certification`.

Certification consumes:

- benchmark evaluation report;
- threat model report;
- reference demo report;
- public documentation index;
- schema-freeze flag.

The required criteria are benchmark evaluation, threat model, reference demo,
public docs, and schema freeze. Any failed required criterion blocks
certification. Failed criteria include deterministic findings, and the release
report publishes evidence-label claims and known limitations.

## Rationale

Certification should be reproducible and auditable. Keeping it as a report over
other reports prevents it from becoming an ungrounded assertion while still
allowing a single release-level decision.

The criteria intentionally mix technical evidence, security review, adoption
surface, and schema stability because a public conclusion release needs all of
those surfaces to be coherent.

## Consequences

Positive:

- Release readiness is represented as JSON and can fail in CI.
- Blocking findings show exactly which criterion failed.
- Public claims remain scoped by evidence labels and known limitations.

Negative:

- Certification cannot be stronger than its inputs.
- Release managers must maintain benchmark, demo, docs, and schema-freeze
  evidence together.

## Alternatives Considered

- Certify from a checklist document. Rejected because checklist prose is not
  enforceable by the release pipeline.
- Require every future formal backend and adapter to be complete before any
  certification. Rejected because the conclusion release is scoped and must
  publish limitations rather than claim universal support.

## Validation

`tests/test_milestone_group7.py` verifies a certified positive path and blocking
behavior for incomplete threat-model evidence and missing schema-freeze
evidence.
