# ADR 0068: Normalized Counterexample Traces And Refusal Output

## Status

Proposed

## Context

Backend counterexamples need a stable shape for refusals, PR comments, and
benchmarks.

## Decision

Normalize formal backend counterexamples into v2 records with source hashes,
backend IDs, steps, excerpts, and metadata.

## Consequences

Different backend output formats can feed the same downstream refusal surface.

## Validation

`nlreq counterexample-normalize-v2` consumes formal backend responses.
