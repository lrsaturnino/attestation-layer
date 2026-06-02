# Phase 71 - Adapter Certification Suite

## Status

Implemented.

## Purpose

Provide a stable certification report for source adapters.

## Implementation

- `nlreq.adapter_certification`
- `nlreq adapter-certify`
- `schemas/adapter-certification-report.schema.json`

Certification evaluates manifest shape, symbol resolution, call graph output,
and trace extraction when trace sources are declared. Levels are
`manifest_only`, `static_resolution`, `trace_capable`, and
`production_candidate`.

## Exit Criteria

- Unresolved or ambiguous required symbols block certification.
- Trace declarations that emit no traces block certification.
- Certification reports input hashes and counts.
