# Phase 143 - Adapter Certification And Plugin SDK

## Status

Implemented.

## Purpose

Make third-party source adapter authoring possible without changing core code,
while keeping certification failure taxonomy and capability declarations
auditable.

## Implementation

Primary module:

- `src/nlreq/adapter_certification.py`

Primary artifacts:

- `AdapterCertificationFixture`
- `AdapterPluginManifest`
- `AdapterPluginValidationReport`
- `AdapterCertificationReport`

Schemas:

- `schemas/adapter-certification-fixture.schema.json`
- `schemas/adapter-plugin-manifest.schema.json`
- `schemas/adapter-plugin-validation-report.schema.json`
- `schemas/adapter-certification-report.schema.json`

CLI:

```bash
uv run nlreq adapter-certify \
  --language go \
  --manifest source-manifest.json \
  --symbol Redeem \
  --required-capability static_symbol_resolution \
  --out certification.json

uv run nlreq adapter-plugin-validate \
  --plugin-manifest adapter-plugin.json \
  --certification-report certification.json \
  --out plugin-validation.json
```

## Plugin Manifest Contract

A plugin manifest records:

- plugin id
- package name
- adapter entry point
- adapter id
- language and runtime
- v2 capability contract
- one or more certification fixtures

Fixtures include:

- source manifest
- required symbols
- required capabilities
- expected minimum certification level

## Contracts

- Plugin capability contract must match the certified adapter contract.
- Plugin adapter id and language must match the certification report.
- Certification must pass before plugin validation accepts the manifest.
- A plugin manifest without fixtures blocks validation.
- Certification fixtures are public SDK inputs and must remain deterministic.
- Certification reports are conformance evidence, not semantic proof.

## Failure Behavior

- Missing fixture: `plugin_sdk` blocking finding.
- Stale or mismatched capability contract: `plugin_sdk` blocking finding.
- Failed certification: `plugin_sdk` blocking finding.
- Adapter id or language mismatch: `plugin_sdk` blocking finding.

## Verification

`tests/test_milestone_group13.py` verifies plugin manifest creation, validation,
missing-fixture blocking, adapter capability CLI output, and v2 certification
compatibility.
