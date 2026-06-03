# Phase 150 - Final Real-Evidence Conclusion Certification

## Status

Implemented.

## Purpose

Certify the scoped real-evidence conclusion release only when all milestone 14
evidence inputs are present, replayable, signed where required, benchmarked,
governed, and free of scaffold evidence.

## Implementation

Primary module:

- `src/nlreq/conclusion_certification.py`

Primary artifact:

- `FinalRealEvidenceConclusionCertificationReport`

Schema:

- `schemas/final-real-evidence-conclusion-certification-report.schema.json`

## Contract

Final certification consumes:

- `CrossLanguageProofObjectV2`;
- `ReplayVerificationReport`;
- `ParallelDispatchPlan`;
- `PublicBenchmarkReleaseReport`;
- `ReferenceBrownfieldPilotReport`;
- `CiPolicyGovernanceReportV2`;
- schema freeze decision;
- release bundle hash;
- signed release bundle hash;
- optional scaffold evidence hashes.

Certification passes only when:

- cross-language causal proof is accepted and closed;
- replay and signing verification is valid;
- performance dispatch is ready and within budget;
- public benchmark report is publishable;
- reference brownfield pilot report is accepted;
- CI policy governance passed;
- schemas are frozen;
- release bundle and signed release bundle hashes are present;
- no scaffold evidence hashes are included.

## Public Claim Boundaries

The certification report records explicit claim boundaries:

- only supported controlled requirements are covered;
- bounded checking remains bounded;
- traces ground observed behavior only;
- adapter certification covers declared capabilities and limitations;
- generated candidate specs remain untrusted unless reviewed and promoted.

## Failure Behavior

Any failed required criterion produces a blocking finding and makes the release
`blocked`. Scaffold evidence is always blocking.

## Verification

`tests/test_milestone_group14.py` verifies successful certification and
blocking behavior when scaffold evidence is present.
