# ADR 0089: Reference Brownfield Demo Selection And Reproducibility Contract

## Status

Accepted

## Context

The conclusion release must demonstrate the attestation layer on a brownfield
system, not only on isolated unit fixtures. The demo needs to exercise code,
requirements, reviewed specs, traces, evidence reports, and reproduction
commands together.

The demo also needs a negative path. A release that only demonstrates accepted
requirements does not prove that the gate can refuse stale, unsupported, or
contradictory evidence.

## Decision

Define a `ReferenceDemoManifest` and `ReferenceDemoReport`.

The manifest records source root, accepted and refused requirements, optional
expected report paths, reviewed system specs, trace artifacts, reproduction
commands, and notes.

The report validates required path presence and decision checks. When an
expected report path is provided, the checker extracts the actual decision and
compares it to the manifest expectation. Missing artifacts, missing report
decisions, decision mismatches, or missing accepted/refused coverage block the
demo report.

Conclusion certification additionally requires at least one declared
reproduction command.

## Rationale

Artifact presence alone is too weak for a release demo. Decision checks prove
that the visible demo result matches the expected accepted/refused outcome.
Keeping expected report paths optional preserves a staged path for early demo
authoring while still allowing certification to demand stronger evidence.

## Consequences

Positive:

- Demo reproducibility is represented as JSON, not informal instructions.
- Accepted and refused requirement paths are both required.
- Decision mismatch failures are precise and reviewable.

Negative:

- Demo maintainers must keep paths and expected decisions current.
- The demo report does not validate the semantic quality of every artifact; it
  validates the reproducibility contract.

## Alternatives Considered

- Use benchmark fixtures as the reference demo. Rejected because benchmark
  cases are focused evaluation units, not a cohesive brownfield adoption story.
- Require every manifest requirement to have a report path at model-validation
  time. Rejected to keep draft demo manifests possible before gate reports are
  generated.

## Validation

`tests/test_milestone_group7.py` verifies successful reproduction, missing
artifact blocking, decision mismatch blocking, and certification dependence on
declared reproduction commands.
