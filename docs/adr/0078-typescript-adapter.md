# ADR 0078: TypeScript Adapter And Async Trace Normalization Policy

## Status

Proposed

## Context

Frontend and service requirements often span TypeScript.

## Decision

Add a TypeScript adapter using static extraction for functions, values, classes,
interfaces, and types. Async trace semantics are represented through normalized
causal trace links, not IR-specific TypeScript constructs.

## Consequences

TypeScript does not leak into the core IR.

## Validation

The adapter is certifiable through the shared suite.
