# Phase 17 Protobuf/gRPC Adapter

Phase 17 adds a protocol/spec adapter for Protobuf/gRPC service contracts.

This phase is implemented in the reference CLI as `protobuf-conformance`,
`protobuf-package`, and `protobuf-validate`.

## Purpose

The phase lets the Attestation Layer say:

```text
This reviewed requirement is linked to this .proto schema,
this RPC, actor, message, field, or transition resolved deterministically,
and this schema hash was checked by the Protobuf/gRPC adapter.
```

It does not say:

```text
The gRPC server implements the RPC correctly.
Authorization interceptors execute at runtime.
The service rejects requests before mutating state.
Clients handle responses correctly.
Transport security is configured correctly.
```

Protobuf/gRPC evidence is declaration-level evidence.

## Why This Comes After Phase 16

OpenAPI, GraphQL, JSON Schema, and AsyncAPI cover request/response, graph API,
payload/data, and event-driven contracts. Protobuf/gRPC is the next
protocol/spec surface because it covers RPC contracts across many
implementation languages while preserving the same dependency-light,
declaration-level evidence boundary.

## CLI Shape

Build a package:

```bash
uv run nlreq protobuf-package tests/fixtures/requirements/authorization_precondition.nlreq \
  --out /tmp/REQ-PROTOBUF-001 \
  --requirement-id REQ-PROTOBUF-001 \
  --title "Unauthorized gRPC operation is rejected before state changes" \
  --claim-kind authorization_precondition \
  --schema tests/fixtures/adapters/protobuf/sample.proto \
  --protobuf-name sample-protobuf
```

Validate a package:

```bash
uv run nlreq protobuf-validate /tmp/REQ-PROTOBUF-001 \
  --schema tests/fixtures/adapters/protobuf/sample.proto \
  --protobuf-name sample-protobuf
```

Run adapter conformance:

```bash
uv run nlreq protobuf-conformance tests/fixtures/adapters/protobuf/sample.proto \
  --protobuf-name sample-protobuf
```

## Supported Schema Shape

The first adapter supports a deterministic `.proto` subset with:

- `package` declarations;
- file-level `option` declarations;
- `message` blocks with scalar and named fields;
- `service` blocks with unary `rpc` declarations;
- RPC-level `option` declarations;
- reviewed auth options: `nlreq.auth_required` or `auth_required`;
- reviewed principal options: `nlreq.actor` or `actor`;
- reviewed state transition options:
  `nlreq.rejects_unauthorized_before`, `rejects_unauthorized_before`,
  `nlreq.state_transition`, or `state_transition`.

## Evidence Semantics

The adapter may produce:

- `TYPE_CHECKED` for schema/binding shape checks;
- `STATICALLY_RESOLVED` for current Protobuf/gRPC symbol bindings and reviewed
  option declarations.

The adapter must not produce:

- `TEST_VALIDATED`;
- `TRACE_VALIDATED`;
- `BOUNDED_CHECKED`;
- `PROVEN_INDUCTIVE`.

## Safety Rules

- Do not infer runtime server behavior from `.proto` declarations.
- Do not treat reviewed `nlreq.*` options as executable proof.
- Do not claim interceptor execution, transport security, streaming behavior,
  client behavior, or state mutation ordering.
- Do not claim request/response semantics beyond declared RPC shapes and
  reviewed options.
- Do not silently accept unsupported claim shapes.
- Do not mutate reviewed packages in place.
- Do not bypass adapter conformance.

## Success Criterion

Phase 17 succeeds when a reviewed requirement can be linked to a Protobuf/gRPC
schema, and:

- Protobuf/gRPC symbols resolve deterministically;
- adapter conformance passes;
- Protobuf/gRPC packages build and validate;
- stale schema hashes are detected;
- package index, gates, continuous reports, and agent handoffs can validate
  Protobuf/gRPC packages when configured;
- unsupported Protobuf/gRPC claim shapes remain explicit;
- and existing generic, Python, OpenAPI, GraphQL, JSON Schema, AsyncAPI,
  command, trace, routing, and TLA workflows remain compatible.

## Boundary

This phase is not a gRPC server adapter, client adapter, interceptor verifier,
transport security checker, streaming semantics checker, or runtime behavior
proof. It adds honest declaration-level Protobuf/gRPC evidence.
