# Phase 145 - Evidence Replay And Signing Enforcement

## Status

Implemented.

## Purpose

Make high-assurance evidence reproducible and anti-forgery hardened by binding
retained artifacts to replay commands, producer identity, and signatures.

## Implementation

Primary modules:

- `src/nlreq/artifact_store.py`
- `src/nlreq/signed_evidence.py`

Primary artifacts:

- `ReplayBundleManifestV2`
- `ReplayCommandMetadata`
- `ReplayVerificationReport`
- `ReplayVerificationFinding`
- `SignedEvidenceEnvelope`
- `ProducerKeyRegistry`

Schemas:

- `schemas/replay-bundle-manifest-v2.schema.json`
- `schemas/replay-verification-report.schema.json`
- `schemas/signed-evidence-envelope.schema.json`
- `schemas/producer-key-registry.schema.json`

## Contract

A v2 replay bundle records:

- bundle id and source artifact store id;
- replay command, working directory, environment, and tool versions;
- retained artifact records;
- signed evidence envelopes for high-assurance artifacts;
- deterministic input hashes.

Replay verification checks:

- every record is present under the bundle root;
- every retained file hashes to its declared artifact hash;
- high-assurance records declare `producer_id` metadata;
- high-assurance records have a signed envelope whose payload names the same
  artifact hash;
- signature keys are registered and trusted for high-assurance evidence;
- the replay command is present.

High-assurance evidence levels are:

- `BOUNDED_CHECKED`
- `PROVEN_INDUCTIVE`

## Failure Behavior

- Missing file: `artifact` finding.
- Hash mismatch: `artifact` finding.
- Missing replay command: `command` finding.
- Missing producer metadata: `producer` finding.
- Producer mismatch: `producer` finding.
- Missing, invalid, unknown, or untrusted signature: `signature` finding.

Any blocking finding makes the verification report `blocked`.

## Verification

`tests/test_milestone_group14.py` verifies valid replay, missing producer,
untrusted key, and missing artifact behavior.
