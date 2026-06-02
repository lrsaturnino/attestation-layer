# ADR 0083: Signed Evidence Envelopes And Producer Attestation Policy

## Status

Proposed

## Context

High-assurance evidence must be protected against tampering and producer
spoofing.

## Decision

Introduce signed evidence envelopes and producer key registries. The first local
implementation uses HMAC-SHA256, with algorithm recorded in the envelope.

## Consequences

Local and CI deployments can verify tampering without adding new dependencies.
Future asymmetric keys can use the same envelope shape.

## Validation

Tests verify valid signatures and trusted-key high-assurance mode.
