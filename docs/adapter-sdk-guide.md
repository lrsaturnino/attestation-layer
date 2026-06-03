# Adapter SDK Guide

Adapters present source code, symbols, traces, and package metadata to the
attestation layer without changing requirement IR semantics.

## Required Contracts

- `schemas/source-manifest.schema.json`
- `schemas/source-symbol-resolution.schema.json`
- `schemas/source-code-presentation.schema.json`
- `schemas/source-call-graph.schema.json`
- `schemas/adapter-capability-contract.schema.json`
- `schemas/adapter-certification-report.schema.json`
- `schemas/adapter-certification-fixture.schema.json`
- `schemas/adapter-plugin-manifest.schema.json`
- `schemas/adapter-plugin-validation-report.schema.json`

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

Capability-aware certification can require adapter features:

```bash
uv run nlreq adapter-certify \
  --language typescript \
  --manifest source-manifest.json \
  --symbol handleRequest \
  --required-capability static_symbol_resolution \
  --required-capability code_presentation \
  --out certification.json
```

## Plugin Manifests

Third-party adapters publish an `AdapterPluginManifest` with:

- plugin id,
- Python package name,
- adapter entry point,
- adapter id, language, and runtime,
- v2 capability contract,
- and at least one certification fixture.

Validate a plugin manifest against a passing certification report:

```bash
uv run nlreq adapter-plugin-validate \
  --plugin-manifest adapter-plugin.json \
  --certification-report certification.json \
  --out plugin-validation.json
```

Plugin validation accepts only when the manifest capability contract matches the
certified adapter contract and fixtures are present.
