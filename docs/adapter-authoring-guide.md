# Adapter Authoring Guide

Adapters connect controlled requirements to one target ecosystem while preserving
the shared package, evidence, and status contract.

## Required Interface

Implement the adapter methods exercised by `nlreq.conformance.assert_adapter_conforms`:

- `resolve_symbol(ref)`: resolve a requirement term to target symbols.
- `validate_binding(ref, symbol)`: verify a proposed binding is legal.
- `evidence_capabilities()`: declare evidence levels the adapter can provide.
- `generate_tasks(ir)`: produce deterministic verification tasks for an IR.
- `run_task(task)`: execute one adapter task and return a backend result.
- `collect_evidence(results)`: normalize backend results.

The generic adapter in `src/nlreq/adapter.py` is the smallest reference. The
Python package adapter in `src/nlreq/python_adapter.py` is the first real
adapter. The OpenAPI adapter in `src/nlreq/openapi_adapter.py` is the second
real adapter and the reference for declaration-level evidence.

## Conformance

Every adapter should have a conformance fixture with:

- one resolvable symbol,
- one unresolved symbol,
- one ambiguous symbol if the ecosystem can produce ambiguity,
- a representative IR.

Run conformance before integrating package generation:

```bash
uv run nlreq python-conformance tests/fixtures/adapters/pythonpkg/samplepkg --package-name samplepkg
uv run nlreq openapi-conformance tests/fixtures/adapters/openapi/sample-openapi.json --openapi-name sample-api
```

## Evidence Rules

Adapters must not inflate evidence levels. Report only what was checked:

- static binding resolution maps to `STATICALLY_RESOLVED`;
- shape/type checks map to `TYPE_CHECKED`;
- scoped passing tests map to `TEST_VALIDATED`;
- generated property checks map to `TEST_VALIDATED` unless a stronger backend
  actually proves the claim;
- trace validation maps to `TRACE_VALIDATED`;
- model checking maps to `BOUNDED_CHECKED` or `PROVEN_INDUCTIVE`.

Backend results should include enough deterministic detail to detect stale
evidence, such as task input hashes and source or test paths.

## Capability Rules

Production source adapters must expose a v2 capability contract through
`capability_contract()`. The contract must:

- list only evidence labels backed by capability claims,
- describe unsupported ecosystem features as limitations,
- distinguish static, trace-capable, and production-candidate support,
- and name trace producers as external where runtime traces are not extracted
  by the adapter itself.

Use required capabilities during certification to prevent accidental evidence
inflation:

```bash
uv run nlreq adapter-certify \
  --language rust \
  --manifest source-manifest.json \
  --symbol redeem \
  --required-capability static_symbol_resolution \
  --required-capability call_graph
```

## Package Integration

Before adding a new adapter-specific package command:

1. Keep `decide_status` pure.
2. Generate tasks deterministically from `RequirementIR`.
3. Store normalized backend results in an adapter-specific artifact if needed.
4. Validate package artifacts by recomputing expected tasks, evidence, and
   status.
5. Add CLI coverage and a fixture package.
6. Add the adapter to the phase documentation.
