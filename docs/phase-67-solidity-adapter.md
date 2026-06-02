# Phase 67 - Solidity Adapter

## Status

Implemented as a static production-adapter contract.

## Purpose

Add an event/transaction-oriented source adapter surface for Solidity without
making the core Solidity-specific.

## Implementation

- `nlreq.production_source_adapters.SoliditySourceAdapter`
- `nlreq adapter-certify --language solidity`
- `schemas/adapter-certification-report.schema.json`

The adapter resolves contracts, libraries, interfaces, functions, events, and
modifiers from project-root-relative source files. Trace extraction delegates to
normalized trace artifacts declared in the source manifest.

## Exit Criteria

- Solidity symbols can be resolved through the common `SourceLanguageAdapter`
  interface.
- Call graph and code presentation use the common source schemas.
- Adapter certification can certify static symbol resolution.
