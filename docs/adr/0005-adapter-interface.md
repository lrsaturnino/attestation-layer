# ADR 0005: Adapter Interface

## Status

Accepted

## Context

The NL Requirement Attestation Layer must remain system-neutral. Target-specific behavior belongs behind adapters; the core owns the IR, package format, evidence taxonomy, and status decision.

## Decision

Adapters implement the interface described in `docs/adapter-interface.md`:

- `resolve_symbols`
- `validate_binding`
- `available_evidence`
- `generate_tasks`
- `collect_evidence`

Every real adapter must pass the adapter conformance suite before its evidence can satisfy gates.

## Consequences

Adapters can vary by ecosystem while sharing the same package/evidence/status contract. The generic Phase 0 adapter is the reference implementation for conformance tests.
