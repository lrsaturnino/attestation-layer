# ADR 0157: Reference Brownfield Demo And Beta Pilots

## Status

Accepted

## Context

The reference demo contract verified reproducibility, but the final release
also needs beta pilot feedback retained as release evidence.

## Decision

Introduce beta pilot findings, beta pilot reports, and a brownfield pilot
release report. The report accepts only when the extended reference demo is
reproducible, pilot reports exist, requirements were exercised, pilots passed,
and blocker-severity findings are mitigated.

## Consequences

Release findings from pilots are retained even when non-blocking. The tradeoff
is that final certification depends on pilot evidence and cannot be certified
from local fixtures alone unless those fixtures include pilot reports.

## Validation

Group 14 tests verify accepted pilot findings and unmitigated blocker refusal.
