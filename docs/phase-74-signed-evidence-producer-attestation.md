# Phase 74 - Signed Evidence And Producer Attestation

## Status

Implemented.

## Purpose

Harden high-assurance evidence against tampering and producer spoofing. A report
that claims a backend, adapter, or trace producer generated evidence must be able
to bind the payload to a registered producer identity.

## Scope

The phase introduces signed evidence envelopes and a producer key registry. The
current implementation uses deterministic HMAC-SHA256 for local developer and CI
validation while keeping algorithm identity explicit for later asymmetric or
hardware-backed signing.

## Data Contracts

- `ProducerKey` records key id, producer id, algorithm, optional public hint,
  and whether the key is trusted for high-assurance evidence.
- `ProducerKeyRegistry` records registered producer keys and requires unique key
  ids.
- `SignedEvidenceEnvelope` records producer id, key id, algorithm, payload hash,
  payload, signature, and tool metadata.
- `SignatureVerificationReport` returns `valid`, `invalid`, `untrusted_key`, or
  `unknown_key` with reasons.

The implemented schemas are:

- `schemas/producer-key-registry.schema.json`
- `schemas/signed-evidence-envelope.schema.json`
- `schemas/signature-verification-report.schema.json`

## API And CLI

Implementation module: `nlreq.signed_evidence`.

Core functions:

- `sign_evidence_payload(...)` canonicalizes and signs a JSON payload.
- `verify_signed_evidence(...)` validates registry membership, producer/key
  binding, trust policy, payload hash, and signature.

CLI:

- `nlreq sign-evidence <payload> --producer-id <id> --key-id <id> --secret <secret> --envelope-id <id>`
- `nlreq verify-evidence <envelope> --registry <registry> --secret <key=secret>`
- `nlreq verify-evidence ... --high-assurance`

## Trust Rules

- A valid signature proves integrity for the signed payload and selected key.
- A valid signature does not prove the payload is semantically correct.
- High-assurance verification requires a registered key marked
  `trusted_for_high_assurance`.
- Unknown keys, unavailable verification secrets, producer/key mismatches,
  payload tampering, and signature mismatches are distinct outcomes.
- Local unsigned evidence remains possible outside high-assurance policy, but it
  must not be mislabeled as signed high-assurance evidence.

## Verification

`tests/test_milestone_group6.py` verifies valid envelopes, tampered payload
detection, and high-assurance trusted-key enforcement.

## Exit Criteria

- Tampered evidence fails verification.
- Unknown and untrusted keys are represented explicitly.
- High-assurance mode can require trusted producer keys.
- Proof closure can record signature status without treating signatures as proof
  of semantic correctness.
