# ADR 0013: Phase 11 Runtime Trace Validation

## Status

Proposed

## Context

Phases 8 and 9 introduced continuous attestation reports, normalized trace
artifact ingestion, and agent handoff payloads. Phase 10 is planned to add a
command/test-runner adapter so brownfield projects can reuse explicit existing
checks as `TEST_VALIDATED` evidence.

Those checks still run mostly before merge or in controlled CI environments.
They do not answer whether the deployed system continues to behave according to
reviewed requirements after release. Runtime behavior can drift because of
configuration changes, dependency changes, data-dependent paths, integration
behavior, or service interactions that test commands did not exercise.

The architecture already reserves `TRACE_VALIDATED`, and Phase 8 already accepts
normalized trace artifacts for reporting. Phase 11 should make that evidence
level real for a narrow, documented trace-validation contract.

## Decision

Phase 11 will introduce runtime trace validation as a gateable evidence backend
over normalized trace artifacts.

The first implementation should target OpenTelemetry-shaped or otherwise
normalized service traces, but the Attestation Layer should validate only its
own normalized trace artifact contract. Raw production payloads, retention,
sampling, and PII handling remain deployment-policy concerns outside reviewed
requirement packages.

The trace validator will accept normalized trace artifacts that include:

- trace id,
- adapter id,
- source or trace hash,
- capture window,
- environment,
- redaction status,
- requirement ids,
- service or component identity,
- ordered events or spans,
- relevant attributes after redaction,
- and provenance for the collector/export path.

The validator may produce `TRACE_VALIDATED` only when:

- the normalized trace artifact validates against the schema,
- redaction status is `redacted` or `not_required`,
- the trace explicitly references the requirement id,
- the requirement claim shape has a documented trace validator,
- the trace contains the event sequence required by that validator,
- the validator records its version and input hashes,
- and the result is bound to the package and trace artifact hashes.

The first supported claim shapes should be narrow:

- authorization rejection was observed before a declared state-change event,
- successful operation emitted a required event,
- operation did not emit a forbidden event in the observed trace,
- and simple ordering constraints over bounded event sequences.

Trace validation proves only observed behavior. It must not claim unobserved
paths are correct, and it must not replace tests, model checking, or proof.

## Planned Artifacts

Trace validation should add or formalize artifacts such as:

```text
normalized-traces.json
trace-validation-tasks.json
trace-validation-results.json
counterexamples.json
evidence.json
status.json
```

The exact filenames may change during implementation, but every gateable result
must be schema-validated and hash-addressed.

Example validation result:

```json
{
  "schema_version": "0.1",
  "adapter": "trace",
  "validator_id": "authorization-before-state-change",
  "requirement_id": "REQ-AUTH-001",
  "trace_id": "trace-2026-05-27-001",
  "status": "valid",
  "evidence_level": "TRACE_VALIDATED",
  "trace_hash": "sha256:...",
  "validator_version": "0.1",
  "observed_events": [
    "request_received",
    "authorization_failed",
    "request_rejected"
  ],
  "forbidden_events_absent": [
    "state_change"
  ]
}
```

## Safety Rules

Runtime trace validation must remain conservative:

- no raw production payloads in requirement packages by default,
- no `TRACE_VALIDATED` from trace presence alone,
- no validation of unredacted traces unless deployment policy explicitly allows
  it,
- no evidence claim without requirement id linkage,
- no claim that sampled traces cover all executions,
- no mutation of historical reviewed packages,
- no hard-gate enforcement until trace-validator false positives are low in
  report-only mode,
- and no trace evidence for claim shapes without a documented validator.

## Consequences

Phase 11 makes continuous attestation substantially more useful because it can
validate observed runtime behavior after merge. It also provides language-neutral
coverage: traces can come from Python, TypeScript, Go, Rust, Solidity indexers,
or any other system that can emit normalized runtime events.

The tradeoff is operational complexity. Trace evidence depends on stable
instrumentation, redaction, sampling policy, environment labeling, and validator
versioning. The system must expose those limits directly instead of hiding them
behind a passing status.
