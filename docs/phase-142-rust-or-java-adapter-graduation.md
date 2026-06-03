# Phase 142 - Rust Or Java Adapter Graduation

## Status

Implemented.

## Purpose

Add a second compiled ecosystem pressure test beyond Go and make overload,
macro, and virtual-dispatch limitations visible at the adapter boundary.

## Implementation

Primary module:

- `src/nlreq/production_source_adapters.py`

Primary adapter selection:

- Rust is the primary phase 142 pressure-test adapter.
- Java remains implemented as a companion compiled-service adapter.

Primary adapters:

- `RustSourceAdapter`
- `JavaSourceAdapter`

CLI:

```bash
uv run nlreq adapter-certify \
  --language rust \
  --manifest rust-source-manifest.json \
  --symbol redeem \
  --required-capability call_graph \
  --out rust-certification.json

uv run nlreq adapter-certify \
  --language java \
  --manifest java-source-manifest.json \
  --symbol redeem \
  --out java-certification.json
```

## Supported Surface

Rust recognizes:

- functions
- structs
- enums
- traits

Java recognizes:

- classes
- interfaces
- enums
- methods

## Contracts

- Rust is declared as `ecosystem=compiled_system`.
- Java is declared as `ecosystem=compiled_service`.
- Rust macro expansion is a limitation until rust-analyzer or compiler-backed
  facts are supplied.
- Java overloads are ambiguity unless a future unique method signature binding
  is supplied.
- Java inheritance and virtual dispatch are declared review-depth limitations
  in this static slice.
- Both adapters consume normalized traces through adapter-local producers.

## Failure Behavior

- Rust macro-expanded symbol: limitation `rust-macro-expansion`, closure effect
  `review`.
- Java overloaded method name: `symbol_resolution` blocking finding.
- Java virtual dispatch depth: limitation `java-inheritance-static-depth`,
  closure effect `review`.

## Verification

`tests/test_milestone_group13.py` verifies Rust certification as the primary
compiled-system pressure test and Java overload blocking as a distinct compiled
service edge case.
