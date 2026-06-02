# Phase 70 - Rust Or Java Adapter

## Status

Implemented for both Rust and Java as static adapter contracts.

## Purpose

Pressure-test the adapter interface against additional compiled ecosystems.

## Implementation

- `nlreq.production_source_adapters.RustSourceAdapter`
- `nlreq.production_source_adapters.JavaSourceAdapter`
- `nlreq adapter-certify --language rust`
- `nlreq adapter-certify --language java`

Rust recognizes functions, structs, enums, and traits. Java recognizes classes,
interfaces, enums, and methods. Both consume normalized traces through the
common SDK path.

## Exit Criteria

- A third ecosystem can use the same manifest, symbol, call graph, code
  presentation, trace, and certification contracts.
- Unsupported semantic depth is visible as adapter limitation, not hidden core
  behavior.
