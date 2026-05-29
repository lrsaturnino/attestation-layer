# ADR 0018: Phase 16 AsyncAPI Adapter

## Status

Proposed

## Context

The protocol/spec adapter portfolio now covers OpenAPI, GraphQL, and JSON
Schema. Event-driven systems still need a declaration-level contract surface for
channels, messages, and publish/subscribe operations. AsyncAPI is the natural
next adapter because it describes event APIs across many implementation
languages.

Runtime event delivery is not guaranteed by an AsyncAPI document. A schema can
declare that an operation publishes a message, but it cannot prove the producer
emits it, a broker delivers it, or consumers process it. The adapter must stay
honest about that boundary.

## Decision

Phase 16 will introduce an AsyncAPI adapter.

The first implementation will:

- parse deterministic JSON AsyncAPI documents;
- resolve symbols for operations, channels, messages, events, and principals;
- support reviewed `x-nlreq-actions` metadata for rollout and ambiguity tests;
- validate bindings against the current document hash;
- generate adapter tasks for symbol shape and event emission declarations;
- produce `STATICALLY_RESOLVED` and `TYPE_CHECKED` evidence only;
- provide `asyncapi-conformance`, `asyncapi-package`, and `asyncapi-validate`
  CLI commands;
- integrate with package index, gate, continuous, and agent workflows through
  the existing adapter validation options;
- and document unsupported AsyncAPI behavior.

The first supported claim shape is:

```text
if actor is approved
then operation must emit operation_accepted
```

The adapter treats AsyncAPI operation/message declarations and
`x-nlreq-actions` as reviewed contract metadata. It will not infer runtime event
delivery, broker behavior, subscriber behavior, ordering, exactly-once
semantics, or payload compatibility beyond the declared message binding.

## Consequences

Phase 16 expands declaration-level evidence from request/response and payload
contracts into event contracts. Teams can bind requirements to AsyncAPI
documents and get deterministic freshness, conformance, and package validation.

The tradeoff is evidence strength. AsyncAPI checks are declaration-level
evidence. Stronger evidence should come from command checks, runtime traces,
broker-specific adapters, consumer tests, or model checks.
