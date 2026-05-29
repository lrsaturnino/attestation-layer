# Phase 14 GraphQL Schema Adapter

Phase 14 adds a protocol/spec adapter for GraphQL SDL schemas.

This phase is implemented in the reference CLI as `graphql-conformance`,
`graphql-package`, and `graphql-validate`.

## Purpose

The phase lets the Attestation Layer say:

```text
This reviewed requirement is linked to this GraphQL schema,
this operation and directive metadata were resolved deterministically,
and this schema hash was checked by the GraphQL adapter.
```

It does not say:

```text
The resolver implementation is correct.
Runtime authorization behavior was observed.
All clients receive the intended error behavior.
```

GraphQL schema evidence is declaration-level evidence.

## Why This Comes After Phase 13

Phases 10 through 13 added broad command checks, runtime traces, routing, and
bounded model checks. The next adapter should expand protocol/spec coverage
without adding a heavy runtime toolchain. GraphQL is a natural follow-on to
OpenAPI because it is another common API contract surface.

## CLI Shape

Build a package:

```bash
uv run nlreq graphql-package tests/fixtures/requirements/authorization_precondition.nlreq \
  --out /tmp/REQ-GRAPHQL-001 \
  --requirement-id REQ-GRAPHQL-001 \
  --title "Unauthorized GraphQL operation is rejected before state changes" \
  --claim-kind authorization_precondition \
  --schema tests/fixtures/adapters/graphql/sample-schema.graphql \
  --graphql-name sample-graphql
```

Validate a package:

```bash
uv run nlreq graphql-validate /tmp/REQ-GRAPHQL-001 \
  --schema tests/fixtures/adapters/graphql/sample-schema.graphql \
  --graphql-name sample-graphql
```

Run adapter conformance:

```bash
uv run nlreq graphql-conformance tests/fixtures/adapters/graphql/sample-schema.graphql \
  --graphql-name sample-graphql
```

## Supported Schema Shape

The first parser supports a deterministic subset of GraphQL SDL:

- `type` and `interface` definitions;
- `Query`, `Mutation`, and `Subscription` fields as operations;
- field return types;
- field directives;
- auth directives such as `@auth`, `@authenticated`, and `@requiresAuth`;
- state-change directives such as `@stateChange(name: "state_change")`.

The first implementation intentionally does not require a full GraphQL parser
dependency. Complex SDL features can be added later if they are needed by real
schemas.

## Evidence Semantics

The adapter may produce:

- `TYPE_CHECKED` for schema/binding shape checks;
- `STATICALLY_RESOLVED` for supported claim checks over schema declarations.

The adapter must not produce:

- `TEST_VALIDATED`;
- `TRACE_VALIDATED`;
- `BOUNDED_CHECKED`;
- `PROVEN_INDUCTIVE`.

## Safety Rules

- Do not infer resolver behavior from SDL alone.
- Do not treat an auth directive as runtime authorization proof.
- Do not claim transport-level HTTP behavior from GraphQL field declarations.
- Do not silently accept unsupported claim shapes.
- Do not mutate reviewed packages in place.
- Do not bypass adapter conformance.

## Success Criterion

Phase 14 succeeds when a reviewed requirement can be linked to a GraphQL schema,
and:

- GraphQL symbols resolve deterministically;
- adapter conformance passes;
- GraphQL packages build and validate;
- stale schema hashes are detected;
- package index, gates, continuous reports, and agent handoffs can validate
  GraphQL packages when configured;
- unsupported GraphQL claim shapes remain explicit;
- and existing generic, Python, OpenAPI, command, trace, routing, and TLA
  workflows remain compatible.

## Boundary

This phase is not a resolver adapter, GraphQL execution engine, contract test
runner, or runtime authorization proof. It adds honest declaration-level
GraphQL schema evidence.
