# ADR 0139: Proof-Producing Backend Boundary

## Status

Accepted

## Context

The project needs a future path to true proof evidence without allowing bounded
model-checker runs to claim inductive proof strength. `PROVEN_INDUCTIVE` must
be tied to proof-assistant producers and retained proof artifacts.

## Decision

Add `ProofProducingBackendBoundaryReport` and `ProofArtifactRef` in
`nlreq.evidence_boundary`.

`PROVEN_INDUCTIVE` is accepted only when all are true:

- backend status is `valid`;
- producer mapping registers the backend as `proof_assistant`;
- a `checked_proof` artifact is retained;
- proof checker command metadata is present.

Bounded evidence produces an informational finding that it is not inductive.

## Consequences

Apalache, TLC, and other model-checker results can support bounded closure but
cannot be promoted into theorem evidence. TLAPS, Lean, Coq, Dafny, or similar
backends can be added later under the same artifact contract.

## Validation

Group 11 tests verify fake inductive claims are blocked and checked
proof-assistant evidence is accepted.
