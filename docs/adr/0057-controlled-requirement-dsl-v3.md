# ADR 0057: Controlled Requirement DSL v3 Grammar, Canonical Form, And Compatibility Policy

## Status

Proposed

## Context

DSL v2 supports a narrow demo fragment. The conclusion front door needs richer
requirement classes while preserving deterministic parsing and source spans.

## Decision

Add DSL v3 as a separate grammar and parser. DSL v3 supports authorization,
state preconditions, postconditions, event/state correspondence, numeric
invariants, bounded temporal properties, and cross-module causal obligations.

The grammar version remains independent from IR version. DSL v3 lowers to
IR 0.2 with deterministic source-span provenance.

Operational rules:

- Canonical text is the source for byte-stable spans and hashing.
- Unsupported grammar constructs fail before IR emission.
- Requirement class and DSL version are recorded in root metadata.
- Each semantic node records deterministic parse provenance.

Rejected alternatives:

- Extending DSL v2 in place was rejected because existing fixtures and package
  consumers rely on DSL v2 compatibility.
- Accepting a broader natural-language-like grammar was rejected because it
  would weaken parser determinism and source-span stability.

Validation:

- `nlreq ir-v3` emits `RequirementIRV2`.
- Golden tests cover every supported requirement class.

## Consequences

Existing DSL v2 commands remain compatible. New product intake can target
DSL v3 without changing the IR schema.
