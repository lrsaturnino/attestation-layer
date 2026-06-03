# ADR 0152: Adapter Certification And Plugin SDK Contract

## Status

Accepted

## Context

Adapter certification existed as a local report, but third-party adapter
authors needed a stable way to publish capability metadata and conformance
fixtures without changing core code.

## Decision

Introduce plugin SDK artifacts:

- `AdapterCertificationFixture`
- `AdapterPluginManifest`
- `AdapterPluginValidationReport`

A plugin manifest binds plugin id, package, entry point, adapter id, language,
runtime, v2 capability contract, and at least one certification fixture.
Validation accepts only when the plugin manifest matches a passing
certification report and includes fixtures.

Certification reports now include capability contract, required capabilities,
missing capabilities, supported evidence, limitation ids, source presentation
counts, trace counts, and plugin SDK compatibility.

## Consequences

Third-party adapters can publish a schema-backed manifest and fixture set that
the core can validate. Certification failures become actionable through
categories such as `capability_contract`, `symbol_resolution`,
`trace_extraction`, and `plugin_sdk`.

The tradeoff is that plugin authors must treat fixtures and capability
contracts as versioned public API, not informal examples.

## Validation

Group 13 tests verify plugin manifest creation, plugin validation acceptance,
missing-fixture blocking, and adapter capability CLI output.
