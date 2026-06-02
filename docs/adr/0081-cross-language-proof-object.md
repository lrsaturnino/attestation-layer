# ADR 0081: Cross-Language Proof Object And Causal Evidence Aggregation

## Status

Proposed

## Context

Requirements can span multiple programming ecosystems.

## Decision

Add a cross-language proof object that references one proof object, source
language slices, trace IDs, causal links, and blockers.

## Consequences

Multi-language closure remains one auditable object without hiding per-adapter
evidence.

## Validation

The CLI builds cross-language proof objects and can fail on blockers.
