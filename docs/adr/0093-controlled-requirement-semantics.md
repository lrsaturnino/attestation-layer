# ADR 0093: Controlled Requirement Semantics

## Status

Proposed

## Context

Controlled-language acceptance requires explicit semantics for every supported
construct. Without a semantics reference, parser acceptance can be mistaken for
formal meaning.

## Decision

Publish a machine-readable DSL v3 semantics reference in
`src/nlreq/controlled_semantics.py`.

The reference lists supported claim classes, canonical rules, required evidence
levels, limitations, construct meanings, and refusal behavior.

## Rejected Alternatives

Keeping semantics only in prose phase docs was rejected because schemas, tests,
and CLI users need a stable artifact.

Treating all parsed DSL v3 constructs as automatically closure-ready was
rejected because temporal and cross-module claims still require explicit
evidence levels and limitations.

## Consequences

Formal claim lowering and documentation can share one source of semantics
truth. The reference must be updated whenever controlled DSL semantics change.

## Validation

`nlreq controlled-semantics` emits the reference. Tests assert all DSL v3 claim
classes and refusal rules are represented.

