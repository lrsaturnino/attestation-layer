# Phase 79 - Threat Model And TCB Audit

## Status

Implemented.

## Purpose

Name the trusted computing base and adversarial evidence scenarios for the
conclusion release.

## Implementation

- `nlreq.threat_model`
- `nlreq threat-model`
- `schemas/threat-model-report.schema.json`

The default threat model covers parser, IR validator, formal backends, source
adapters, trace producers, artifact store, and CI gate. Scenarios cover forged
evidence, stale specs, malicious adapters, and prompt injection.

## Exit Criteria

- High-assurance claims can point to TCB assumptions.
- Benchmark-required adversarial scenarios are named.
- Residual risks are explicit.
