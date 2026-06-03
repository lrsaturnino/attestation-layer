# ADR 0131: Requirement Contradiction Taxonomy

## Status

Accepted

## Context

Requirement self-consistency checks already detected several contradictions,
but the real-evidence roadmap requires a documented ALICE-style taxonomy and a
clear boundary for LLM-assisted suggestions.

## Decision

Publish taxonomy version `alice-style-0.1` through
`build_requirement_contradiction_taxonomy` and include taxonomy metadata in
`RequirementSelfConsistencyResult`.

Untrusted contradiction suggestions are retained as audit hints but cannot
change the self-consistency status.

## Invariants

- Deterministic contradiction classes block closure.
- Backend counterexamples block closure when reported.
- Untrusted suggestions never pass or fail a requirement by themselves.
- Results record taxonomy version and checked codes.

## Consequences

Self-consistency reports now explain which contradiction classes were checked
and preserve optional advisory findings without trusting them.

## Rejected Alternatives

Letting LLM suggestions produce blocking contradictions was rejected because
suggestions are not deterministic evidence.

Keeping contradiction classes implicit in code was rejected because release
reviewers need a stable taxonomy.

## Validation

`tests/test_milestone_group10.py` verifies taxonomy exposure and that untrusted
suggestions do not block an otherwise valid backend result.
