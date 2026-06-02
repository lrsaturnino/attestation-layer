# ADR 0125: Extended Conclusion Certification

## Status

Accepted

## Context

The original conclusion certification checks benchmark, threat model, reference
demo, public docs, and schema freeze. The extended release requires a stronger
bar that includes the hardened gate, CI hard-gate adoption, benchmark
dimensions, replayable demo evidence, documentation freeze, TCB review,
producer evidence, and release bundle signing.

## Decision

Add `ExtendedConclusionCertificationReport`.

Certification consumes:

- extended end-to-end gate report;
- extended CI report;
- extended benchmark report;
- extended reference demo report;
- public documentation freeze report;
- extended TCB review report;
- schema freeze flag;
- producer evidence flag;
- release bundle hash;
- signed release bundle hash unless explicitly waived.

Any failed required criterion blocks certification. Release certification
requires CI mode `hard_gate` with blocking enforcement.

## Rationale

The conclusion claim is only as strong as its release evidence. A single
certification artifact over all group 9 reports gives the release a
reproducible stop condition while preserving known limitations and evidence
label boundaries.

## Consequences

Positive:

- The extended release cannot certify with soft-gate-only adoption.
- Missing producer, schema, or bundle evidence blocks certification.
- Evidence labels and limitations remain attached to the certification report.

Negative:

- Certification requires more artifacts than the first conclusion release.

## Validation

`tests/test_milestone_group9.py` verifies a certified path and blocking behavior
for soft-gate CI, missing schema freeze, missing producer evidence, and missing
release bundle hashes.
