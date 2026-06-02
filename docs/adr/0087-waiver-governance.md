# ADR 0087: Gate Policy, Waiver Governance, And Exception Audit Semantics

## Status

Proposed

## Context

Real adoption needs exceptions, but exceptions must remain visible and bounded.

## Decision

Add a waiver audit report that checks policy allowance, expiration, and hard-gate
safety flags.

## Consequences

Waivers can support staged adoption without making blocked proofs appear closed.

## Validation

Tests cover active waiver audit behavior.
