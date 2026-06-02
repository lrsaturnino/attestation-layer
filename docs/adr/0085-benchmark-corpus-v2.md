# ADR 0085: Benchmark Corpus v2 Methodology And Regression Policy

## Status

Proposed

## Context

The seed benchmark needs release-quality metrics and false-closure tracking.

## Decision

Add benchmark v2 metrics over the existing corpus and result shape. Track
closure rate, false-closure rate, false-refusal rate, runtime, budgets, and
tag-based category counts.

## Consequences

Release claims can budget false closure explicitly.

## Validation

`nlreq benchmark-v2` fails when metrics exceed configured budgets.
