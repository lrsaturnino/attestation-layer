# ADR 0060: Multi-Pass Translator Workbench And Untrusted Candidate Policy

## Status

Proposed

## Context

The existing translator path is deterministic. A production NL front door needs
multiple candidate strategies without trusting stochastic output.

## Decision

Represent translation as a run containing candidate artifacts. Each candidate
records strategy, method, source hash, replay metadata, and optional approval.

Candidate comparison feeds the existing translation agreement report. LLM
candidates cannot be selected without explicit approval.

## Consequences

The system can experiment with LLM translation while keeping the formal trust
boundary deterministic and review-bound.
