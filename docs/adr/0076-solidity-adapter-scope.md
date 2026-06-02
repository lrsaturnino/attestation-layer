# ADR 0076: Solidity Adapter Scope, Tooling, And Trace Semantics

## Status

Proposed

## Context

The roadmap needs an event/transaction-oriented adapter without making the core
Solidity-specific.

## Decision

Add a Solidity source adapter using the common adapter protocol. It performs
static symbol extraction and consumes normalized trace artifacts.

## Consequences

Solidity support is available through the adapter boundary. Deep Slither or
Foundry integrations can replace static extraction later without changing core
schemas.

## Validation

Certification tests cover static Solidity symbol resolution.
