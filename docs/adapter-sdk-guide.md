# Adapter SDK Guide

Adapters present source code, symbols, traces, and package metadata to the
attestation layer without changing requirement IR semantics.

## Required Contracts

- `schemas/source-manifest.schema.json`
- `schemas/source-symbol-resolution.schema.json`
- `schemas/source-code-presentation.schema.json`
- `schemas/source-call-graph.schema.json`
- `schemas/adapter-certification-report.schema.json`

## Authoring Rules

- Report unsupported and ambiguous symbols explicitly.
- Keep adapter-specific locators inside source artifacts, not requirement IR.
- Preserve source paths, spans, module ids, and symbol names needed for review.
- Emit trace producer metadata when the adapter can extract runtime behavior.
- Pass certification fixtures before the adapter is used in high-assurance
  closure.

## Certification

The certification suite checks static resolution, source presentation, and
declared adapter identity. Certification is evidence of contract conformance,
not a proof that every program behavior in the ecosystem is modeled.
