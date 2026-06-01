# ADR 0048: Delta Extraction Taxonomy

## Status

Proposed

## Context

The verification pipeline now emits structured refusals from translation
agreement, self-consistency, system consistency, coverage, trace replay,
extraction, and drift checks. Reviewers need a stable way to convert those
failures into work items without losing the source artifact that caused the
refusal.

## Decision

Introduce a delta report.

Each delta records:

- stable id;
- category: requirement, spec, code, test, or trace;
- severity: blocking or review;
- source report;
- summary;
- required action;
- refs for requirement ids, module ids, trace ids, statuses, or other stable
  identifiers.

The extractor consumes available reports and emits deterministic JSON plus a
human-readable markdown summary. It does not mutate code or specs.

## Consequences

Failed closure can now produce senior-review-grade action items. Later PR or
backlog integrations can consume the JSON without having to understand every
upstream artifact shape.

The taxonomy is intentionally compact. Future phases can add ownership metadata
or richer counterexample projection while preserving the core categories.
