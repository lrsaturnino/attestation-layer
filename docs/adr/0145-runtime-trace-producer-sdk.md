# ADR 0145: Runtime Trace Producer SDK

## Status

Accepted

## Context

Runtime traces are only credible when the producer, runtime, lossiness, replay
inputs, and signature policy are explicit. A trace file by itself is not enough
for high-assurance closure.

## Decision

Extend `nlreq.runtime_trace_sdk` with producer evidence classification.

Trace producers declare identity, adapter, language, runtime, producer kind,
real-producer status, replay retention, and optional signing key id. Extraction
results retain normalized trace hashes, replay input hashes, runtime metadata,
loss records, and signing key metadata. `TraceProducerEvidenceReport` classifies
whether the extraction can support closure.

## Consequences

High-assurance policies can block lossy traces, missing replay inputs, unsigned
producer evidence, and non-real producers before trace validation attempts to
use the traces.

## Validation

Group 12 tests verify replay input retention and lossy high-assurance blocking.
