# Phase 44 End-To-End Requirement Gate

Phase 44 packages the verification workflow behind one command and one final
decision artifact.

## Purpose

The phase lets the Attestation Layer say:

```text
This requirement was parsed, translated, checked, linked to source/spec/trace
evidence, closed as a proof object, and gated for downstream action by one
product-grade workflow.
```

It does not say:

```text
Every unknown can be automatically resolved.
Intermediate artifacts may be skipped.
Downstream action can proceed without a closed proof.
```

## Implementation Scope

Phase 44 implementation includes:

- end-to-end gate report model and schema;
- gate runner API for controlled-text intake;
- CLI command for `requirement-gate`;
- artifact directory with hash-linked intermediate outputs;
- deterministic translation agreement using two parser passes;
- requirement self-consistency execution;
- source impact and contextual source impact execution;
- spec coverage, trace alignment, and trace replay;
- system consistency check;
- delta extraction;
- proof object construction and closure gate evaluation;
- final `accepted`, `refused`, or `unknown` decision.

## Decision Semantics

The gate accepts only when all required stages pass and the closure gate passes.

The gate refuses when a stage finds an actionable failed condition, such as a
trace replay violation, missing coverage, system counterexample, blocked proof,
or blocked closure gate.

The gate returns unknown when a stage cannot decide safely, such as translator
review need, unsupported self-consistency, timeout, or tool error.

`downstream_action_allowed` is true only for `accepted`.

## Artifact Contract

Every intermediate artifact is written to the gate artifact directory and listed
in the final report with a content hash. The final report is the action API
surface; consumers do not infer actionability from a single intermediate file.

## Success Criterion

Phase 44 succeeds when:

- one CLI command can produce a structured acceptance/refusal/unknown report;
- all intermediate artifacts are persisted and hash-linked;
- downstream action remains blocked unless the proof object is closed and the
  closure gate passes.

## Boundary

This phase orchestrates existing deterministic components. It does not replace
individual reports, and it does not hide intermediate failures behind the final
decision.
