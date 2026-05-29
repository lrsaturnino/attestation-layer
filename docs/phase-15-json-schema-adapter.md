# Phase 15 JSON Schema Adapter

Phase 15 adds a protocol/spec adapter for JSON Schema documents.

This phase is implemented in the reference CLI as `json-schema-conformance`,
`json-schema-package`, and `json-schema-validate`.

## Purpose

The phase lets the Attestation Layer say:

```text
This reviewed requirement is linked to this JSON Schema document,
these schema properties and reviewed action metadata resolved deterministically,
and this schema hash was checked by the JSON Schema adapter.
```

It does not say:

```text
The producer implementation always emits this shape.
The consumer implementation validates the schema at runtime.
The database or event bus enforces this contract.
```

JSON Schema evidence is declaration-level evidence.

## Why This Comes After Phase 14

OpenAPI and GraphQL cover two major API contract styles. JSON Schema is the next
small, deterministic protocol/spec surface because it covers payloads,
configuration, event documents, and data contracts used across many languages.

## CLI Shape

Build a package:

```bash
uv run nlreq json-schema-package tests/fixtures/requirements/state_postcondition.nlreq \
  --out /tmp/REQ-JSON-SCHEMA-001 \
  --requirement-id REQ-JSON-SCHEMA-001 \
  --title "Approved operation sets accepted status" \
  --claim-kind state_postcondition \
  --schema tests/fixtures/adapters/jsonschema/sample-schema.json \
  --json-schema-name sample-json-schema
```

Validate a package:

```bash
uv run nlreq json-schema-validate /tmp/REQ-JSON-SCHEMA-001 \
  --schema tests/fixtures/adapters/jsonschema/sample-schema.json \
  --json-schema-name sample-json-schema
```

Run adapter conformance:

```bash
uv run nlreq json-schema-conformance tests/fixtures/adapters/jsonschema/sample-schema.json \
  --json-schema-name sample-json-schema
```

## Supported Schema Shape

The first adapter supports JSON documents with:

- root `properties`;
- nested `properties`;
- `type` declarations;
- `const` and `enum` value declarations;
- `x-nlreq-symbol-type` for reviewed symbol classification;
- `x-nlreq-actions` for reviewed action metadata.

The action metadata is intentionally explicit. A package can say that the schema
declares:

```json
{
  "x-nlreq-actions": {
    "operation": {
      "sets": {
        "operation_status": "accepted"
      },
      "increases": {
        "counter": 1
      }
    }
  }
}
```

## Evidence Semantics

The adapter may produce:

- `TYPE_CHECKED` for schema/binding shape checks;
- `STATICALLY_RESOLVED` for current JSON Schema symbol bindings.

The adapter must not produce:

- `TEST_VALIDATED`;
- `TRACE_VALIDATED`;
- `BOUNDED_CHECKED`;
- `PROVEN_INDUCTIVE`.

## Safety Rules

- Do not infer runtime producer or consumer behavior from schema declarations.
- Do not treat `x-nlreq-actions` as executable proof.
- Do not claim schema enforcement unless a command check, trace, or runtime
  adapter supplies that evidence.
- Do not silently accept unsupported claim shapes.
- Do not mutate reviewed packages in place.
- Do not bypass adapter conformance.

## Success Criterion

Phase 15 succeeds when a reviewed requirement can be linked to a JSON Schema
document, and:

- JSON Schema symbols resolve deterministically;
- adapter conformance passes;
- JSON Schema packages build and validate;
- stale schema hashes are detected;
- package index, gates, continuous reports, and agent handoffs can validate
  JSON Schema packages when configured;
- unsupported JSON Schema claim shapes remain explicit;
- and existing generic, Python, OpenAPI, GraphQL, command, trace, routing, and
  TLA workflows remain compatible.

## Boundary

This phase is not a JSON Schema validator runtime, data producer adapter,
consumer adapter, database adapter, event-bus adapter, or contract test runner.
It adds honest declaration-level JSON Schema evidence.
