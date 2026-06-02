# Phase 74 - Signed Evidence And Producer Attestation

## Status

Implemented.

## Purpose

Harden evidence against tampering and forgery where high-assurance policy
requires signatures.

## Implementation

- `nlreq.signed_evidence`
- `nlreq sign-evidence`
- `nlreq verify-evidence`
- `schemas/signed-evidence-envelope.schema.json`
- `schemas/producer-key-registry.schema.json`
- `schemas/signature-verification-report.schema.json`

The local implementation uses HMAC-SHA256 envelopes for deterministic developer
and CI validation. The schema leaves algorithm identity explicit so asymmetric
or hardware-backed keys can be added without changing evidence payloads.

## Exit Criteria

- Tampered payloads fail verification.
- Unknown or untrusted keys are distinct outcomes.
- High-assurance verification can require trusted keys.
