# Static Adapter Template

Use this template when creating a source adapter that resolves symbols from a
static manifest.

## Minimal Flow

1. Emit a `SourceManifest` with modules, paths, and symbols.
2. Implement symbol resolution against that manifest.
3. Return ambiguity and unsupported outcomes explicitly.
4. Run adapter certification with representative symbol references.

Relevant schemas:

- `schemas/source-manifest.schema.json`
- `schemas/source-symbol-resolution.schema.json`
- `schemas/adapter-certification-report.schema.json`
