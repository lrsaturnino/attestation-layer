# ADR 0074: Runtime Trace Extraction SDK And Trace Producer Metadata

## Status

Proposed

## Context

Trace replay needs real registered producers, not anonymous fixtures.

## Decision

Add a trace producer registry and extraction request/result schema. The first
producer implementation reads normalized local JSON artifacts.

## Consequences

Trace extraction is producer-identified and hash-linked while remaining adapter
neutral.

## Validation

Tests cover registered local extraction.
