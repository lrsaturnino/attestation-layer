# ADR 0083: Signed Evidence Envelopes And Producer Attestation Policy

## Status

Accepted

## Context

Evidence producer validation checks producer metadata, but high-assurance modes
also need tamper detection and a stronger binding between payloads and producer
identity. Unsigned local evidence can be useful during development, but CI and
release certification need a policy knob for trusted producer keys.

## Decision

Introduce signed evidence envelopes and producer key registries in
`nlreq.signed_evidence`.

The first implementation uses HMAC-SHA256 to avoid new dependencies and make
tests deterministic. The envelope records the algorithm explicitly so future
asymmetric or hardware-backed keys can be added without changing payload shape.

Verification returns one of:

- `valid`
- `invalid`
- `untrusted_key`
- `unknown_key`

High-assurance verification requires the registry key to be marked
`trusted_for_high_assurance`.

## Rationale

HMAC-SHA256 is sufficient for local and CI tamper detection while the trust model
is being hardened. Recording algorithm and key identity prevents the signature
format from becoming implicit or magic.

## Consequences

Positive:

- Tampered payloads fail verification.
- Unknown keys and untrusted keys are distinct outcomes.
- High-assurance mode can require trusted producer keys.

Negative:

- HMAC requires verifier access to a shared secret and is not appropriate as the
  final public signing mechanism.
- A valid signature proves payload integrity, not semantic correctness.

## Alternatives Considered

- Require asymmetric signatures immediately. Rejected for this phase because it
  would add dependency and key-management complexity before the envelope policy
  was proven.
- Treat producer ids as sufficient. Rejected because ids alone do not detect
  tampering or spoofing.

## Validation

`tests/test_milestone_group6.py` covers valid signatures, payload tampering, and
high-assurance trusted-key enforcement.
