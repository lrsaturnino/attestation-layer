# ADR 0070: Proof-Level Evidence Boundary And Inductive-Proof Producer Policy

## Status

Proposed

## Context

Bounded model checking and trace replay are valuable but are not inductive
proofs.

## Decision

Add a proof evidence boundary report. `PROVEN_INDUCTIVE` is accepted only from a
registered proof-assistant producer.

## Consequences

Release claims can be strict about the difference between bounded evidence and
proof.

## Validation

`nlreq proof-evidence-boundary` emits blocking findings for invalid proof labels.
