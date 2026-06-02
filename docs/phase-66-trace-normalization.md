# Phase 66 - Trace Normalization

## Status

Implemented.

## Purpose

Normalize runtime-specific trace events into the common trace schema while
recording lossy normalization.

## Implementation

- `nlreq.trace_normalization`
- `nlreq trace-normalize`
- `schemas/raw-trace-artifact.schema.json`
- `schemas/trace-normalization-report.schema.json`

Raw trace events become normalized trace events. Adapter-specific `raw_` fields
are retained in metadata and recorded as loss records.

## Exit Criteria

- Lossy normalization is visible.
- Normalized traces carry adapter, language, runtime, and source hash.
- The report can feed trace extraction and trace replay paths.
