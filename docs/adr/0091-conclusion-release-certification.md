# ADR 0091: Conclusion Release Criteria, Certification Process, And Public Claim Boundaries

## Status

Proposed

## Context

The conclusion roadmap needs a formal stop condition.

## Decision

Add a conclusion certification report over benchmark evaluation, threat model,
reference demo, public docs, and schema freeze evidence.

## Consequences

Certification becomes reproducible and can fail when any required criterion
fails. Known limitations and evidence-label claims ship with the report.

## Validation

`nlreq conclusion-certify` emits a blocking or certified report.
