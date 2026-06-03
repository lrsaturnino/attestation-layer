# ADR 0158: CI Adoption And Policy Governance Hardening

## Status

Accepted

## Context

Hard-gate CI reports can still be misused if the host repository does not make
the check required, waivers are unaudited, or policy changes are unreviewed.

## Decision

Introduce `CiPolicyGovernanceReportV2`. Governance requires hard-gate blocking
CI, stable JSON, host branch protection containing the required check name,
passing waiver audit, audited CI waiver ids, and reviewed policy changes.

## Consequences

The release can claim branch-protection readiness only when host policy
evidence is present. The tradeoff is that governance now depends on external
repository configuration evidence rather than only local CI output.

## Validation

Group 14 tests verify branch protection and policy-review blocking behavior.
