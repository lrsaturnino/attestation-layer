# Phase 29 Agnostic Wedge

Phase 29 proves the architecture is not a one-language or one-formalism tool. A
closed proof object can now be checked for an agnostic wedge: either it spans at
least two source languages or it spans at least two formal targets.

This phase does not add a second production adapter or a second proof backend.
It adds the deterministic report that proves when the existing abstraction has
actually crossed one of those boundaries.

## Purpose

The phase lets the Attestation Layer say:

```text
The requirement is closed by one proof object, and that closure is shown across
more than one source language or more than one formal target.
```

It does not say:

```text
All language adapters are complete.
All formal backends agree on full semantics.
Cross-language trace causality is solved by the IR itself.
```

## Implementation Scope

Phase 29 implementation should include:

- agnostic wedge report model and schema;
- source-language slice extraction from source manifests;
- formal-target slice extraction from formal backend responses;
- closed-proof-object requirement;
- semantic IR boundary scan for adapter-specific metadata;
- explicit limitations for the axis not demonstrated;
- CLI command and tests.

## Evidence Semantics

The wedge passes only when:

- the proof object is `closed`;
- at least two distinct source languages or two distinct formal targets are
  present;
- formal backend responses, when supplied, are `valid` and appear in the proof
  object;
- and adapter-specific facts are not embedded in semantic IR metadata.

The wedge is architectural evidence. It does not increase the evidence level of
the proof object.

## Success Criterion

Phase 29 succeeds when:

- one closed proof object can demonstrate a cross-language or cross-formalism
  wedge;
- source and formal target details stay outside the IR spine;
- unsupported limitations are explicit in the report;
- and the report is schema-backed and CLI-addressable.

## Boundary

This phase is not full cross-language program analysis, not multi-backend proof
agreement, and not a new adapter rollout. Those remain future expansions built
on the source adapter, formal backend, and proof closure boundaries.
