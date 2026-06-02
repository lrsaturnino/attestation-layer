# Phase 57 - TLC Backend Production Integration

## Status

Implemented as a production wrapper contract.

## Purpose

Provide an explicit-state TLA checking path alongside Apalache while preserving
the same evidence and artifact semantics.

## Implementation

- `nlreq.formal_backend.TlcProductionBackend`
- `nlreq formal-backend-check --backend tlc`
- Shared formal backend request/response schemas

The TLC backend uses the same TLA projection artifact as Apalache and invokes a
TLC command through the model-checker runner. Custom commands can be supplied for
tests and controlled deployments.

## Evidence Rules

TLC runs produce bounded evidence only for real valid or counterexample
outcomes. Missing tools and unsupported fragments block closure.

## Exit Criteria

- TLC appears in the formal backend registry.
- Custom checker command fixtures can produce a valid bounded result.
- Counterexamples and unsupported markers remain normalized by the shared runner.
