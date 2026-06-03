# ADR 0154: Evidence Replay And Signing Enforcement

## Status

Accepted

## Context

Retained artifacts and signed envelopes existed separately. The final
real-evidence claim needs one replay verifier that checks retained bytes,
producer identity, and signatures for high-assurance evidence.

## Decision

Introduce v2 replay bundle manifests and verification reports. High-assurance
artifacts marked as `BOUNDED_CHECKED` or `PROVEN_INDUCTIVE` require producer
metadata and a trusted registered signature over a payload naming the artifact
hash.

## Consequences

Release certification can distinguish missing artifacts, tampered bytes,
missing producer identity, unknown keys, untrusted keys, and invalid
signatures. The tradeoff is that high-assurance producers must publish stable
key ids and replay payload metadata.

## Validation

Group 14 tests verify valid replay, missing producer, untrusted key, and
missing artifact behavior.
