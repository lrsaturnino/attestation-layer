# ADR 0017: Phase 15 JSON Schema Adapter

## Status

Proposed

## Context

The adapter portfolio now includes Python source, OpenAPI contracts, GraphQL
schemas, command checks, runtime traces, routing, and TLA+ model checks. The
next useful expansion should keep adding high-leverage protocol/spec evidence
without introducing a language runtime or external service dependency.

JSON Schema is a common contract surface for payloads, configuration, events,
and storage-shaped documents. It can declare required properties, primitive
types, constants, enums, and project-reviewed extension metadata. A JSON Schema
adapter can provide honest declaration-level evidence for requirements that are
about payload state and numeric fields.

The adapter should not claim that a producer, consumer, database, or service
implementation obeys the schema at runtime. It can only say that the reviewed
schema document and reviewed `x-nlreq-actions` metadata contain the declarations
required by the supported claim shape.

## Decision

Phase 15 will introduce a JSON Schema adapter.

The first implementation will:

- parse deterministic JSON Schema documents from JSON;
- resolve symbols for schemas, reviewed actions, principals, fields, state
  fields, and numeric fields;
- validate bindings against the current schema hash;
- generate adapter tasks for symbol shape, state value, and numeric delta
  declarations;
- produce `STATICALLY_RESOLVED` and `TYPE_CHECKED` evidence only;
- provide `json-schema-conformance`, `json-schema-package`, and
  `json-schema-validate` CLI commands;
- integrate with package index, gate, continuous, and agent workflows through
  the existing adapter validation options;
- and document unsupported JSON Schema behavior.

The first supported claim shapes are:

```text
if actor is approved
then operation must set operation_status to "accepted"
```

and:

```text
if counter is at most limit
then operation must increase counter by 1
```

The adapter treats `x-nlreq-actions` as reviewed schema metadata. It will not
infer producer behavior, consumer behavior, persistence behavior, event
delivery, or runtime validation enforcement from the schema alone.

## Consequences

Phase 15 expands spec-level coverage to payload and event schemas while keeping
the adapter-neutral evidence model intact. Teams can attach reviewed
requirements to JSON Schema documents and receive deterministic freshness and
binding validation.

The tradeoff is evidence strength. JSON Schema checks are declaration-level
evidence. Stronger evidence should come from command checks, runtime traces,
language adapters, contract tests, or model checks.
