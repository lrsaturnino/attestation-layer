# Phase 39 Delta Extractor

Phase 39 turns failed verification artifacts into deterministic action items for
reviewers and automation. It separates requirement, spec, code, test, and trace
deltas so failed closure can become actionable work instead of an opaque red
status.

## Purpose

The phase lets the Attestation Layer say:

```text
These checks failed, and these concrete requirement/spec/code/test/trace deltas
must be addressed before proof closure can proceed.
```

It does not say:

```text
The proposed action is automatically correct.
The system can edit code or specs without review.
Every delta has a single owner.
```

## Implementation Scope

Phase 39 implementation includes:

- delta item and delta report models;
- deterministic extraction from self-consistency, system consistency, spec
  coverage, trace replay, and spec drift reports;
- category and severity assignment;
- stable JSON output plus markdown rendering;
- CLI command for `delta-extract`;
- tests for blocking deltas, green reports, markdown, and CLI output.

## Evidence Semantics

Delta extraction does not approve anything. It is a refusal surface that explains
what must change. Proof closure remains blocked until the upstream reports pass.

## Success Criterion

Phase 39 succeeds when:

- failed closure inputs produce stable action items;
- reports distinguish requirement, spec, code, test, and trace categories;
- counterexample and drift sources are visible in refs;
- JSON and markdown outputs are deterministic and CLI-addressable.

## Boundary

This phase does not apply fixes. It packages failed verification evidence into a
reviewable worklist for humans and downstream automation.
