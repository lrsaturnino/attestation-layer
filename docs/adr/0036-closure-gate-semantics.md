# ADR 0036: Closure Gate Semantics

## Status

Proposed

## Context

Earlier hard gates can require accepted package status, but the gap-closure
roadmap needs a stronger downstream gate: action should depend on a closed proof
object, not on scattered evidence files.

## Decision

Add a closure gate report.

The gate passes only when the proof object status is `closed` and it carries no
closure blockers. The first downstream action label is free-form, with `merge`
as the CLI default, so the same report shape can guard PR merge, backlog
promotion, release approval, or deployment promotion.

The closure gate does not mutate package status and does not create waivers.
Existing hard-gate policy remains the scoped CI enforcement layer; the closure
gate is the proof-specific predicate it may require.

## Consequences

Downstream automation has a single deterministic artifact to inspect. Open,
blocked, missing-context, timeout, unsupported, counterexample, or stale
coverage states cannot silently pass as closure.
