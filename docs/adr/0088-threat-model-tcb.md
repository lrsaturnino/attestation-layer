# ADR 0088: Threat Model, TCB Boundary, And Adversarial Evidence Policy

## Status

Proposed

## Context

Conclusion claims require a named trusted computing base and adversarial model.

## Decision

Publish a machine-readable threat model covering TCB components, threats,
mitigations, residual risks, and benchmark-required scenarios.

## Consequences

Security review can reason about parser, IR validator, backend, adapter, trace,
artifact, registry, and CI trust assumptions.

## Validation

`nlreq threat-model` emits the default TCB and threat scenarios.
