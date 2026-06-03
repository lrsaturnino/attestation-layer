# Phase 136 - Runtime Trace Producer SDK Production

## Status

Implemented.

## Purpose

Make runtime trace extraction evidence explicit about producer identity,
runtime metadata, lossiness, replay inputs, and signing requirements.

## Implementation

Primary module:

- `src/nlreq/runtime_trace_sdk.py`

Primary artifacts:

- `TraceProducerRegistry`
- `TraceExtractionRequest`
- `TraceExtractionResult`
- `TraceProducerEvidenceReport`
- `TraceLossRecord`

Schemas:

- `schemas/trace-producer-registry.schema.json`
- `schemas/trace-extraction-result.schema.json`
- `schemas/trace-producer-evidence-report.schema.json`

CLI:

```bash
uv run nlreq trace-extract \
  --registry trace-producers.json \
  --producer-id trace:python \
  --trace-source traces.json \
  --run-id RUN-001 \
  --out trace-extraction.json

uv run nlreq trace-producer-evidence \
  --registry trace-producers.json \
  --producer-id trace:python \
  --extraction-result trace-extraction.json \
  --high-assurance \
  --require-signature \
  --out trace-producer-evidence.json
```

## Contracts

- Producers declare adapter, language, runtime, producer kind, real-producer
  status, replay retention, and optional signing key.
- Extraction results retain normalized trace hash and replay input hashes.
- Loss records are derived from trace and event loss metadata.
- High-assurance closure blocks lossy traces.
- Signature-required policy blocks producers without a signing key.
- Replay-required policy blocks extraction results without replay input hashes.

## Failure Behavior

- Non-real producer: closure `block`.
- Extraction without normalized traces: closure `block`.
- Lossy high-assurance trace: closure `block`.
- Missing signature when required: closure `block`.
- Missing replay inputs when required: closure `block`.

## Verification

`tests/test_milestone_group12.py` verifies replay input retention and
high-assurance lossy trace blocking.
