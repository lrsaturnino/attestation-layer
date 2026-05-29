# ADR 0019: Phase 17 Protobuf/gRPC Adapter

## Status

Proposed

## Context

The protocol/spec adapter portfolio now covers OpenAPI, GraphQL, JSON Schema,
and AsyncAPI. gRPC services commonly use Protobuf files as their reviewed API
contract, so requirements need a declaration-level adapter that can bind to
services, RPCs, messages, fields, and reviewed options without depending on a
language runtime.

A `.proto` file does not prove server behavior. It can declare RPC shapes and
reviewed metadata, but it cannot prove authorization checks run, state changes
are ordered correctly, clients handle errors, or transport policy is enforced.
The adapter must keep that boundary explicit.

## Decision

Phase 17 will introduce a Protobuf/gRPC adapter.

The first implementation will:

- parse a deterministic `.proto` subset without new runtime dependencies;
- resolve symbols for schemas, messages, fields, RPCs, principals, and state
  transitions;
- support reviewed `nlreq.*` options for authorization and state-transition
  metadata;
- validate bindings against the current schema hash;
- generate adapter tasks for symbol shape, auth rejection declarations, and RPC
  response declarations;
- produce `STATICALLY_RESOLVED` and `TYPE_CHECKED` evidence only;
- provide `protobuf-conformance`, `protobuf-package`, and `protobuf-validate`
  CLI commands;
- integrate with package index, gate, continuous, and agent workflows through
  the existing adapter validation options;
- and document unsupported Protobuf/gRPC behavior.

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

The adapter treats RPC declarations and reviewed options as contract metadata.
It will not infer server implementation behavior, interceptor execution,
transport security, authorization policy correctness, streaming semantics,
client behavior, or runtime state changes.

## Consequences

Phase 17 expands declaration-level protocol/spec evidence into gRPC contracts.
Teams can bind requirements to `.proto` files and get deterministic freshness,
conformance, and package validation.

The tradeoff is evidence strength. Protobuf/gRPC checks are declaration-level
evidence. Stronger evidence should come from command checks, runtime traces,
language-specific server adapters, integration tests, or model checks.
