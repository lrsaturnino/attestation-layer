# Phase 41 Real Evidence Producers

Phase 41 adds explicit validation for high-assurance evidence producers. Backend
results that claim bounded or proof-level evidence must come from registered
real producers and include reproducibility metadata.

## Purpose

The phase lets the Attestation Layer say:

```text
This high-assurance evidence was emitted by a registered real producer with a
tool version, command metadata, and input/output or artifact hashes.
```

It does not say:

```text
The evidence is independently re-run.
Manual labels can claim high assurance.
Producer identity alone proves correctness.
```

## Implementation Scope

Phase 41 implementation includes:

- evidence producer validation report model and schema;
- validation against the existing producer mapping;
- high-assurance checks for real producer identity;
- producer-to-evidence-level enforcement;
- tool-version, command, and hash metadata checks;
- CLI command for `evidence-producers-validate`;
- tests for valid bounded evidence, forged high-assurance evidence, missing
  reproducibility metadata, low-assurance bypass, and CLI output.

## Evidence Semantics

`BOUNDED_CHECKED` and `PROVEN_INDUCTIVE` require real producer validation.
Low-assurance context remains outside this check. A valid producer validation
report does not prove the claim by itself; it verifies that the evidence artifact
is eligible to participate in proof closure.

## Success Criterion

Phase 41 succeeds when:

- high-assurance backend results are checked against producer policy;
- forged or manually edited high-assurance evidence is blocked;
- reproducibility metadata is required;
- the validation report is schema-backed and CLI-addressable.

## Boundary

This phase validates producer metadata. It does not re-run external tools or
attest binaries cryptographically.
