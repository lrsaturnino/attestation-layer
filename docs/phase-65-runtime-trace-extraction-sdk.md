# Phase 65 - Runtime Trace Extraction SDK

## Status

Implemented.

## Purpose

Define the producer-facing SDK boundary for real runtime trace extraction.

## Implementation

- `nlreq.runtime_trace_sdk`
- `nlreq trace-extract`
- `schemas/trace-producer-registry.schema.json`
- `schemas/trace-extraction-result.schema.json`

The first producer implementation is a local JSON producer. It validates a
registered producer ID, reads normalized traces, stamps adapter/language/runtime
metadata, and returns extracted, unsupported, or invalid status.

## Exit Criteria

- Unknown producer IDs are refused.
- Missing trace files are unsupported, not success.
- Extracted traces are hash-linked.
