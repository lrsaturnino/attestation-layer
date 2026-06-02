# ADR 0047: Source Impact Analysis And Semantic-Disagreement Policy

## Status

Proposed

## Context

The first source impact analyzer used deterministic call graph expansion from
input symbols. That was useful, but later phases need better brownfield
targeting before spec coverage and extraction: runtime traces may touch modules
outside the static path, and semantic tools may suggest additional modules that
should be reviewed without being trusted as proof.

## Decision

Introduce a contextual source impact analysis artifact.

The analyzer records:

- deterministic modules from source manifest and call graph expansion;
- trace-touched modules from normalized trace metadata;
- optional semantic suggestions;
- disagreements where semantic or trace-only modules fall outside deterministic
  impact;
- call graph edges and input symbols.

Deterministic source structure remains the approving basis. Semantic suggestions
are report-only context. Runtime trace touchpoints broaden affected modules for
review and coverage, but disagreement is preserved rather than hidden.

## Consequences

Coverage, extraction, and drift checks can consume a richer impact report while
still distinguishing deterministic facts from semantic suggestions. Reviewers
can see where runtime behavior or semantic hints disagree with static impact.

Future adapter-specific import analysis can strengthen deterministic impact
without changing the disagreement contract.
