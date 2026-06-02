# ADR 0079: Third Production Adapter Selection And Interface Pressure Test

## Status

Proposed

## Context

A third ecosystem is needed to test whether the adapter interface generalizes.

## Decision

Implement static Rust and Java adapter contracts. Both use the same manifest,
symbol, call graph, presentation, and trace APIs.

## Consequences

The project can test compiled ecosystem shape without committing to one as the
only third adapter.

## Validation

Both languages are accepted by `adapter-certify-v2`.
