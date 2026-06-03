# Phase 138 - Adapter Interface v2 Capability Contract

## Status

Implemented.

## Purpose

Make source adapters production-certifiable by requiring machine-readable
capability claims, evidence labels, limitations, and failure behavior.

## Implementation

Primary modules:

- `src/nlreq/source_adapter.py`
- `src/nlreq/adapter_certification.py`
- `src/nlreq/production_source_adapters.py`

Primary artifacts:

- `AdapterCapabilityContract`
- `AdapterCapabilityClaim`
- `AdapterCapabilityRegistry`
- `AdapterLimitation`
- `AdapterCertificationReport`

Schemas:

- `schemas/adapter-capability-contract.schema.json`
- `schemas/adapter-capability-registry.schema.json`
- `schemas/adapter-certification-report.schema.json`

CLI:

```bash
uv run nlreq adapter-capabilities --language solidity --out solidity-capabilities.json

uv run nlreq adapter-certify \
  --language solidity \
  --manifest source-manifest.json \
  --symbol requestRedemption \
  --required-capability static_symbol_resolution \
  --required-capability code_presentation \
  --out adapter-certification.json
```

## Capability Contract

Each v2 adapter declares:

- `schema_version=0.2`
- `interface_version=2.0`
- adapter identity, language, runtime, and ecosystem
- required interface methods
- capability claims
- supported evidence labels
- supported symbol types and trace runtimes
- limitations with closure effects
- failure taxonomy

Supported capability ids are:

- `manifest`
- `binding_validation`
- `static_symbol_resolution`
- `call_graph`
- `code_presentation`
- `source_impact`
- `coverage_mapping`
- `normalized_trace`
- `runtime_trace_extraction`
- `specula_candidate_extraction`

## Contracts

- `supported_evidence` must be backed by at least one capability claim.
- Certification can require specific capability ids.
- Missing required capabilities block certification.
- Required methods named by the contract must be callable.
- Adapter limitations are part of the certified output.
- Capability metadata is adapter evidence. It does not prove program behavior.

## Failure Behavior

- Missing capability: `result=blocked`, category `capability_contract`.
- Missing required method: `result=blocked`, category `capability_contract`.
- Manifest adapter mismatch: `result=blocked`, category `manifest`.
- Manifest language mismatch: `result=blocked`, category `manifest`.
- Unsupported ecosystem feature: represented as an adapter limitation with
  closure effect `unsupported`, `review`, or `block`.

## Verification

`tests/test_milestone_group13.py` verifies v2 contract fields, required
capability enforcement, source presentation checks, and schema-backed
certification output.
