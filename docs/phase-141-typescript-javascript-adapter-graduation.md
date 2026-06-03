# Phase 141 - TypeScript And JavaScript Adapter Graduation

## Status

Implemented.

## Purpose

Cover frontend and service runtimes through the same adapter interface while
keeping dynamic JavaScript behavior explicit instead of silently overclaiming
static certainty.

## Implementation

Primary module:

- `src/nlreq/production_source_adapters.py`

Primary adapters:

- `TypeScriptSourceAdapter`
- `JavaScriptProductionSourceAdapter`

Schemas:

- `schemas/source-manifest.schema.json`
- `schemas/source-symbol-resolution.schema.json`
- `schemas/source-call-graph.schema.json`
- `schemas/adapter-capability-contract.schema.json`
- `schemas/adapter-certification-report.schema.json`

CLI:

```bash
uv run nlreq adapter-certify \
  --language typescript \
  --manifest ts-source-manifest.json \
  --symbol handleRequest \
  --required-capability static_symbol_resolution \
  --out typescript-certification.json

uv run nlreq adapter-certify \
  --language javascript \
  --manifest js-source-manifest.json \
  --symbol handleClick \
  --out javascript-certification.json
```

## Supported Surface

TypeScript recognizes:

- functions
- exported variables
- classes
- interfaces
- type declarations

JavaScript recognizes:

- functions
- exported variables
- classes

Both adapters declare browser, Node, and OpenTelemetry trace runtimes through
the normalized trace contract.

## Contracts

- TypeScript is declared as `ecosystem=frontend_service`.
- JavaScript is declared as `ecosystem=dynamic_scripting`.
- Compiler API and source-map depth remain adapter-local future tooling; the
  core consumes only normalized source and trace artifacts.
- Dynamic imports, computed exports, monkey patching, and `eval` are explicit
  limitations.
- Unsupported dynamic JavaScript cannot produce static closure without external
  evidence.

## Failure Behavior

- Unresolved static symbol: `symbol_resolution` blocking finding.
- Unsupported dynamic export pattern: limitation
  `javascript-dynamic-properties`, closure effect `unsupported`.
- Missing browser or Node trace producer output: `trace_extraction` blocking
  finding when trace sources are declared.

## Verification

`tests/test_milestone_group13.py` verifies TypeScript static certification,
JavaScript production routing, and explicit unsupported dynamic-pattern
limitations.
