# ADR 0066: TLC Backend Contract And Explicit-State Checking Policy

## Status

Proposed

## Context

Explicit-state checking provides a second TLA execution path and a useful
comparison point for symbolic checking.

## Decision

Introduce `TlcProductionBackend` with backend ID `tlc`. It shares projection,
artifact, runner, and evidence semantics with the Apalache backend.

## Consequences

TLC can be configured independently without changing proof closure. Unsupported
and missing-tool outcomes remain non-approving.

## Validation

Tests cover custom command execution and bounded evidence mapping.
