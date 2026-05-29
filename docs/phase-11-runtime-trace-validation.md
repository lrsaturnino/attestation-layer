# Phase 11 Runtime Trace Validation

Phase 11 should make `TRACE_VALIDATED` evidence real for a narrow, documented
runtime trace-validation contract.

This phase is implemented in the reference CLI as `trace-validate`, with
continuous-attestation integration behind `--trace-validation`.

## Purpose

The phase should let the Attestation Layer say:

```text
This reviewed requirement was observed in this normalized trace,
captured from this environment and time window,
with redaction and provenance recorded,
and validated by this trace validator.
```

It should not say:

```text
All production behavior is correct.
All unobserved paths satisfy the requirement.
The implementation is proven.
```

Trace validation proves only observed behavior.

## Why This Comes After Phase 10

Phase 10 gives broad brownfield coverage by linking requirements to explicit
project commands and test runners. Phase 11 extends coverage after merge by
validating observed staging or production behavior.

Together they form a practical sequence:

```text
reviewed requirement
  -> command/test evidence before merge
  -> runtime trace evidence after merge
  -> continuous attestation trend over time
```

## Planned CLI Shape

Example trace validation:

```bash
uv run nlreq trace-validate requirements \
  --requirement-id REQ-AUTH-001 \
  --trace-artifact /tmp/normalized-traces.json \
  --out /tmp/nlreq-trace-validation.json \
  --markdown-out /tmp/nlreq-trace-validation.md
```

Example continuous attestation with gateable trace validation:

```bash
uv run nlreq continuous-attestation requirements \
  --trigger schedule \
  --trace-artifact /tmp/normalized-traces.json \
  --trace-validation \
  --out /tmp/nlreq-continuous-with-trace-validation.json
```

Trace validation remains explicit: traces are provided with `--trace-artifact`,
and continuous attestation only validates them when `--trace-validation` is set.

## Normalized Trace Input

The input should reuse and tighten the existing `NormalizedTraceArtifact`
contract. A usable trace artifact must include:

- `trace_id`,
- `adapter_id`,
- `source_hash` or trace hash,
- `events`,
- `requirement_ids`,
- `environment`,
- `capture_window`,
- `redaction.status`,
- service or component identity,
- and collector/export provenance.

Allowed redaction status values for gateable evidence should initially be:

- `redacted`
- `not_required`

Other redaction states may be report-only findings.

## First Validator Shapes

The first validators should be deliberately narrow:

| Claim Pattern | Trace Validator |
|---|---|
| Unauthorized action is rejected before state change | Observe rejection event and absence of state-change event before trace end. |
| Successful operation emits required event | Observe operation success and required event in order. |
| Operation does not emit forbidden event | Observe operation window and absence of forbidden event. |
| Bounded event ordering | Check event A occurs before event B within one trace. |

These validators are enough to prove the trace path works without introducing a
general temporal-logic engine.

## Planned Result Artifact

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

Invalid traces should produce structured counterexamples with the missing,
misordered, contradictory, or forbidden events.

## Evidence Semantics

The adapter may produce `TRACE_VALIDATED` only when:

- the trace artifact validates against schema,
- the trace explicitly references the requirement id,
- the requirement claim has a supported trace validator,
- redaction status is acceptable,
- the validator actually checks the required event relation,
- package and trace hashes are recorded,
- and validator version and configuration are recorded.

Trace validation must not satisfy:

- `TEST_VALIDATED`,
- `BOUNDED_CHECKED`,
- or `PROVEN_INDUCTIVE`.

## Integration Points

Phase 11 should integrate with:

- `continuous-attestation`, so scheduled runs can report trace regressions;
- `hard-gate`, as an optional policy input after report-only burn-in;
- `agent-verify`, so trace failures become reviewer handoffs or coder retry
  payloads;
- `attestation-artifact-catalog`, so trace validation artifacts are documented;
- and future adapter routing, so trace adapters can be selected by required
  evidence level.

## Safety Rules

- Do not store raw production payloads in requirement packages by default.
- Do not claim coverage beyond observed traces.
- Do not treat sampled traces as exhaustive.
- Do not run hard-gate enforcement until report-only mode shows acceptable
  stability.
- Do not validate unredacted sensitive data unless deployment policy explicitly
  allows it.
- Do not mutate historical packages in place.
- Do not let trace presence alone satisfy evidence.

## Success Criterion

Phase 11 succeeds when a normalized trace artifact can be validated against at
least one reviewed requirement, and:

- valid traces produce `TRACE_VALIDATED` evidence;
- invalid traces produce structured counterexamples;
- missing, unredacted, unknown, stale, or unsupported traces are visible
  findings;
- continuous attestation can include trace-validation results;
- agent verifier handoffs can surface trace failures clearly;
- hard gates can opt into trace-validation findings after report-only rollout;
- and existing generic, Python, OpenAPI, and command/test-runner workflows remain
  unchanged.

## Boundary

This phase is not TLA+, full temporal logic, production observability storage,
or proof of all runtime behavior. It is a narrow bridge from reviewed
requirements to observed runtime traces.
