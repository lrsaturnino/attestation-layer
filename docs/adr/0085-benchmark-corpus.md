# ADR 0085: Benchmark Evaluation Methodology And Regression Policy

## Status

Proposed

## Context

The seed benchmark needs release-quality metrics and false-closure tracking.

## Decision

Add benchmark evaluation metrics over the existing corpus and result shape. Track
closure rate, false-closure rate, false-refusal rate, runtime, budgets, and
tag-based category counts.

## Consequences

Release claims can budget false closure explicitly.

## Validation

`nlreq benchmark-evaluate` fails when metrics exceed configured budgets.
