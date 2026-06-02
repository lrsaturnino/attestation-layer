# ADR 0075: Normalized Trace Schema v2 And Lossy-Normalization Policy

## Status

Proposed

## Context

Different runtimes expose different trace details, and normalization may lose
adapter-specific semantics.

## Decision

Add a raw trace artifact and normalization report. Raw adapter-specific metadata
is retained but recorded as lossy when it cannot become common schema fields.

## Consequences

Trace consumers can see what was normalized and what remained runtime-specific.

## Validation

Tests cover lossy records for `raw_` metadata.
