# Phase 139 - Solidity Adapter Graduation

## Status

Implemented.

## Purpose

Graduate the transaction/event ecosystem adapter so EVM contracts can
participate in the same adapter capability, symbol, trace, and certification
contracts as non-EVM ecosystems.

## Implementation

Primary module:

- `src/nlreq/production_source_adapters.py`

Primary adapter:

- `SoliditySourceAdapter`

Schemas:

- `schemas/source-manifest.schema.json`
- `schemas/source-symbol-resolution.schema.json`
- `schemas/source-call-graph.schema.json`
- `schemas/source-code-presentation.schema.json`
- `schemas/adapter-capability-contract.schema.json`
- `schemas/adapter-certification-report.schema.json`

CLI:

```bash
uv run nlreq adapter-certify \
  --language solidity \
  --manifest solidity-source-manifest.json \
  --symbol requestRedemption \
  --required-capability static_symbol_resolution \
  --required-capability normalized_trace \
  --out solidity-certification.json
```

## Supported Surface

The graduation slice recognizes:

- contracts
- libraries
- interfaces
- functions
- events
- modifiers

The adapter marks Solidity as `ecosystem=transaction_event`, `runtime=evm`,
and trace runtimes `evm`, `foundry`, and `debug_traceTransaction`.

## Contracts

- Overloaded function names are ambiguous unless a future binding strategy
  supplies a unique source identity.
- Event symbols carry adapter-local metadata such as `binding_role=event`.
- Transaction and event traces are consumed through normalized trace artifacts.
- Solidity-specific facts remain in source, trace, and certification artifacts;
  they do not enter requirement IR.
- Inheritance, virtual dispatch, and modifier expansion are declared as
  review-depth limitations in this implementation slice.

## Failure Behavior

- Duplicate or overloaded symbol name: `symbol_resolution` blocking finding.
- Missing trace source file: `trace_extraction` blocking finding.
- Trace source declared but no normalized trace emitted: `trace_extraction`
  blocking finding.
- Inheritance or modifier semantic depth: recorded as limitation
  `solidity-inheritance-static-depth`.

## Verification

`tests/test_milestone_group13.py` verifies overloaded Solidity symbols block
certification, event binding metadata is retained, transaction traces normalize
through the shared trace schema, and a trace-backed Solidity fixture reaches
`production_candidate`.
