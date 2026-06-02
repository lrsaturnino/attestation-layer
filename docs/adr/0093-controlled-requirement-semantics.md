# ADR 0093: Controlled Requirement Semantics

## Status

Accepted

## Context

Controlled-language acceptance requires explicit semantics for every supported
construct. Without a semantics reference, parser acceptance can be mistaken for
formal meaning.

## Decision

Publish a machine-readable DSL v3 semantics reference in
`src/nlreq/controlled_semantics.py`.

The reference lists supported claim classes, canonical rules, required evidence
levels, limitations, construct meanings, and refusal behavior.

The reference is emitted through `nlreq controlled-semantics` and captured by
`schemas/controlled-requirement-semantics.schema.json`.

## Decision Details

The semantics reference is the source of truth for group-8 lowering and
documentation. It covers:

- authorization preconditions;
- state preconditions;
- state postconditions;
- numeric invariants;
- event/state correspondence;
- bounded temporal properties;
- cross-module causal obligations.

Each construct states its formal role, allowed claim classes, required evidence,
canonical meaning, and refusal behavior. This makes parser acceptance distinct
from closure readiness.

## Invariants

- Every accepted DSL v3 claim class has a canonical semantic rule.
- Every construct that creates bounded or trace-grounded obligations records the
  required evidence.
- Bounded temporal semantics never imply inductive proof.
- Unsupported grammar is refused before semantic-tree construction.
- Unsupported semantic nodes are refused before backend projection.

## Rejected Alternatives

Keeping semantics only in prose phase docs was rejected because schemas, tests,
and CLI users need a stable artifact.

Treating all parsed DSL v3 constructs as automatically closure-ready was
rejected because temporal and cross-module claims still require explicit
evidence levels and limitations.

## Consequences

Formal claim lowering and documentation can share one source of semantics
truth. The reference must be updated whenever controlled DSL semantics change.

This increases documentation burden but removes an important ambiguity: accepted
controlled syntax is no longer treated as self-explanatory.

## Compatibility

The artifact is additive for existing DSL v3 users. Semantic meaning changes are
not backward-compatible unless they are versioned in the reference and covered
by migration tests.

## Validation

`nlreq controlled-semantics` emits the reference. Tests assert all DSL v3 claim
classes and refusal rules are represented.
