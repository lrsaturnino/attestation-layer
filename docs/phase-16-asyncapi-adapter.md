# Phase 16 AsyncAPI Adapter

Phase 16 adds a protocol/spec adapter for AsyncAPI event contracts.

This phase is implemented in the reference CLI as `asyncapi-conformance`,
`asyncapi-package`, and `asyncapi-validate`.

## Purpose

The phase lets the Attestation Layer say:

```text
This reviewed requirement is linked to this AsyncAPI document,
this operation and event message resolved deterministically,
and this document hash was checked by the AsyncAPI adapter.
```

It does not say:

```text
The service actually publishes the event at runtime.
The broker delivers the event.
Consumers process the event correctly.
Events are ordered or exactly-once.
```

AsyncAPI evidence is declaration-level evidence.

## Why This Comes After Phase 15

OpenAPI, GraphQL, and JSON Schema cover request/response, graph API, and
payload/data contracts. AsyncAPI is the next protocol/spec surface because it
covers event-driven APIs while preserving the same dependency-light,
declaration-level evidence boundary.

## CLI Shape

Build a package:

```bash
uv run nlreq asyncapi-package tests/fixtures/requirements/event_emit.nlreq \
  --out /tmp/REQ-ASYNCAPI-001 \
  --requirement-id REQ-ASYNCAPI-001 \
  --title "Approved operation emits accepted event" \
  --claim-kind event_state_correspondence \
  --document tests/fixtures/adapters/asyncapi/sample-asyncapi.json \
  --asyncapi-name sample-event-api
```

Validate a package:

```bash
uv run nlreq asyncapi-validate /tmp/REQ-ASYNCAPI-001 \
  --document tests/fixtures/adapters/asyncapi/sample-asyncapi.json \
  --asyncapi-name sample-event-api
```

Run adapter conformance:

```bash
uv run nlreq asyncapi-conformance tests/fixtures/adapters/asyncapi/sample-asyncapi.json \
  --asyncapi-name sample-event-api
```

## Supported Document Shape

The first adapter supports JSON AsyncAPI documents with:

- top-level `asyncapi`, `info`, `channels`, `operations`, and `components`;
- component messages under `components.messages`;
- channel messages under `channels.*.messages`;
- top-level operations with `action`, `channel`, and `messages`;
- AsyncAPI 2-style channel `publish` and `subscribe` operation objects;
- security schemes under `components.securitySchemes`;
- reviewed `x-nlreq-actions` metadata for explicit action-to-event links.

## Evidence Semantics

The adapter may produce:

- `TYPE_CHECKED` for document/binding shape checks;
- `STATICALLY_RESOLVED` for current AsyncAPI symbol bindings.

The adapter must not produce:

- `TEST_VALIDATED`;
- `TRACE_VALIDATED`;
- `BOUNDED_CHECKED`;
- `PROVEN_INDUCTIVE`.

## Safety Rules

- Do not infer runtime event delivery from AsyncAPI declarations.
- Do not treat `x-nlreq-actions` as executable proof.
- Do not claim broker, subscriber, ordering, or exactly-once behavior.
- Do not claim payload compatibility beyond the declared message reference.
- Do not silently accept unsupported claim shapes.
- Do not mutate reviewed packages in place.
- Do not bypass adapter conformance.

## Success Criterion

Phase 16 succeeds when a reviewed requirement can be linked to an AsyncAPI
document, and:

- AsyncAPI symbols resolve deterministically;
- adapter conformance passes;
- AsyncAPI packages build and validate;
- stale document hashes are detected;
- package index, gates, continuous reports, and agent handoffs can validate
  AsyncAPI packages when configured;
- unsupported AsyncAPI claim shapes remain explicit;
- and existing generic, Python, OpenAPI, GraphQL, JSON Schema, command, trace,
  routing, and TLA workflows remain compatible.

## Boundary

This phase is not an event broker adapter, producer adapter, consumer adapter,
payload validator runtime, or event-delivery proof. It adds honest
declaration-level AsyncAPI evidence.
