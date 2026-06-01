# ADR 0060: Multi-Pass Translator Workbench And Untrusted Candidate Policy

## Status

Proposed

## Context

The existing translator path is deterministic. A production NL front door needs
multiple candidate strategies without trusting stochastic output.

## Decision

Represent translation as a run containing candidate artifacts. Each candidate
records strategy, method, source hash, replay metadata, and optional approval.

The product CLI emits at least two deterministic candidates by default: a DSL
v3 parser candidate and a rule-based post-processor candidate over canonical
controlled text. Candidate comparison feeds the existing translation agreement
report. LLM candidates cannot be selected without explicit approval.

Operational rules:

- Candidate generation is stored separately from candidate selection.
- The selected candidate hash is recorded in a selection artifact.
- A deterministic parser candidate can be replayed from source text and tool
  metadata.
- Candidate source hashes must match the run source hash before comparison or
  selection.
- LLM candidates are allowed as candidate artifacts only; they do not become
  trusted formal artifacts by generation.

Rejected alternatives:

- A single best-effort translator output was rejected because disagreements and
  ambiguity would be hidden.
- Trusting an LLM candidate by default was rejected because formal checks must
  consume reviewed deterministic artifacts.

Validation:

- Candidate comparison uses the same structural agreement contract as earlier
  translation phases.
- Single-candidate runs remain `needs_review` until another agreement path or
  explicit selection resolves them.
- Multi-pass CLI runs should be comparison-ready without external services.

## Consequences

The system can experiment with LLM translation while keeping the formal trust
boundary deterministic and review-bound.
