# Phase 140 - Go Adapter Graduation

## Status

Implemented.

## Purpose

Graduate a compiled service ecosystem adapter and prove that the source adapter
interface is not transaction- or scripting-specific.

## Implementation

Primary module:

- `src/nlreq/production_source_adapters.py`

Primary adapter:

- `GoSourceAdapter`

Primary artifacts:

- `SourceManifest`
- `SourceCallGraph`
- `CodePresentation`
- `AdapterCapabilityContract`
- `AdapterCertificationReport`

CLI:

```bash
uv run nlreq adapter-capabilities --language go --out go-capabilities.json

uv run nlreq adapter-certify \
  --language go \
  --manifest go-source-manifest.json \
  --symbol Redeem \
  --required-capability call_graph \
  --required-capability normalized_trace \
  --out go-certification.json
```

## Supported Surface

The graduation slice recognizes:

- Go functions
- Go methods
- Go type declarations
- module/package ids from source manifests
- normalized runtime traces from runtime/trace or OpenTelemetry producers

## Contracts

- Go is declared as `ecosystem=compiled_service`.
- Call graph output uses the shared `SourceCallGraph` schema.
- Package graph information is emitted as adapter metadata.
- Runtime traces must already be normalized by a registered trace producer.
- Build tags, generated files, and generic instantiation are limitations of the
  static slice and require review or deeper adapter tooling.
- Specula-style extraction remains untrusted candidate generation and is not a
  direct adapter proof.

## Failure Behavior

- Missing required symbol: `symbol_resolution` blocking finding.
- Ambiguous symbol: `symbol_resolution` blocking finding.
- Missing trace producer output: `trace_extraction` blocking finding.
- Build tag or generated-code uncertainty: limitation
  `go-build-tags-and-generics`, closure effect `review`.

## Verification

`tests/test_milestone_group13.py` verifies Go static call graph edges, package
metadata, normalized trace stamping, and `production_candidate` certification.
