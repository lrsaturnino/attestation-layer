# ADR 0016: Phase 14 GraphQL Schema Adapter

## Status

Proposed

## Context

Phases 10 through 13 added broad command evidence, runtime trace validation,
adapter routing, and bounded TLA+ model-checking evidence. The next useful
adapter expansion should add another protocol/spec surface without taking on a
large language runtime or cross-system proof contract.

OpenAPI already covers REST-style API contracts. Many services expose GraphQL
schemas instead, where the reviewed contract is a schema document containing
queries, mutations, return types, and directives. A GraphQL adapter can extend
the same conservative declaration-level evidence model to those services.

The adapter should not claim that a GraphQL resolver implementation is correct.
It can only say that the reviewed schema declares the operation, auth
directives, return shape, and state-change metadata required by the supported
claim shape.

## Decision

Phase 14 will introduce a GraphQL schema adapter.

The first implementation will:

- parse a deterministic subset of GraphQL SDL;
- resolve symbols for operations, auth principals, fields, and declared
  state-change metadata;
- validate bindings against the current schema hash;
- generate adapter tasks for symbol shape, auth directive checks, and operation
  return shape checks;
- produce `STATICALLY_RESOLVED` or `TYPE_CHECKED` evidence only;
- provide `graphql-conformance`, `graphql-package`, and `graphql-validate` CLI
  commands;
- integrate with package index, gate, continuous, and agent workflows through
  the existing adapter validation options;
- and document unsupported GraphQL behavior.

The first supported claim shapes are:

```text
if actor is not authorized
then operation must be rejected before state_change
```

and:

```text
if actor is approved
then operation must succeed
```

The adapter will treat auth and state-change directives as reviewed schema
metadata. It will not infer resolver behavior, database writes, transport
status codes, or runtime authorization behavior from the schema alone.

## Consequences

Phase 14 increases protocol/spec coverage while keeping the adapter-neutral
evidence model intact. Teams with GraphQL APIs can produce deterministic
requirement packages without waiting for a TypeScript, Go, Rust, or Python
resolver adapter.

The tradeoff is evidence strength. GraphQL schema checks are declaration-level
evidence. Stronger evidence should come from command checks, runtime trace
validation, resolver-specific language adapters, or model checks.
