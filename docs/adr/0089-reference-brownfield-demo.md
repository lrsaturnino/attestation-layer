# ADR 0089: Reference Brownfield Demo Selection And Reproducibility Contract

## Status

Proposed

## Context

Synthetic fixtures are not enough for conclusion credibility.

## Decision

Define a reference demo manifest with source root, accepted and refused
requirements, specs, traces, commands, and reproducibility notes.

## Consequences

The demo can be checked for artifact presence and included in certification.

## Validation

`reference-demo-check` reports missing artifacts and requires both accepted and
refused requirement entries.
