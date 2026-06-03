# ADR 0126: Production Free-Form Intake Runtime

## Status

Accepted

## Context

The real-evidence roadmap requires a product-quality path from human input to
approved controlled requirements. Existing intake artifacts retained original
text and proposals, but they did not model runtime state transitions or the
selected approved controlled text hash.

## Decision

Adopt an explicit free-form intake runtime record with drafted, proposed,
approved, rejected, and superseded states.

The runtime record selects exactly one approved controlled rewrite by proposal
ID and controlled text hash. Semantic translation can require that exact hash
before parsing.

## Invariants

- Raw free-form text is evidence only.
- Rejected rewrite proposals cannot be selected.
- Superseded intake records cannot transition further.
- Approved selection is bound to proposal ID, original text hash, controlled
  text hash, and diff hash.
- Every state transition records actor, timestamp, reason, and artifact hashes.

## Consequences

Downstream tooling can distinguish raw intake retention from approved controlled
input. The parser can fail closed when a caller omits the approved text hash.

## Rejected Alternatives

Using proposal status alone was rejected because it does not preserve an audit
trail of runtime transitions or selected proposal state.

Allowing parser calls to infer approval from text content was rejected because
content equality without review provenance is not enough evidence.

## Validation

`tests/test_milestone_group10.py` covers approved runtime selection, rejected
proposal refusal, and hash-bound downstream parsing.
