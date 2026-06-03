# ADR 0140: Production Source Impact Semantics

## Status

Accepted

## Context

Brownfield closure requires knowing which code a requirement touches before the
tool can evaluate coverage, freshness, and traces. The old impact report mixed
deterministic module impact with contextual hints without a closure policy.

## Decision

Add `ProductionSourceImpactReport` in `nlreq.source_impact`.

The report separates:

- adapter-resolved symbols;
- deterministic modules from call graph expansion;
- dependency modules;
- trace-touched modules;
- non-gateable semantic suggestions;
- findings with `blocking`, `review`, or `info` severity.

Unresolved and ambiguous input symbols block closure. Trace-only impact and
semantic suggestions require review unless policy changes the confidence rules.

## Consequences

Coverage and trace gates can consume `affected_modules` without trusting LLM
impact hints. Reviewers still see semantic suggestions and trace disagreements
when adapter impact may be incomplete.

## Validation

Group 12 tests verify deterministic impact, review findings, and symbol
resolution blockers.
