# Phase 7 OpenAPI Adapter Expansion

Phase 7 adds the second real adapter selected in ADR 0009: OpenAPI documents.

## Implemented Slice

- OpenAPI JSON document loading
- simple OpenAPI YAML document loading for deterministic in-repo fixtures
- deterministic symbol discovery for paths, operations, operation ids,
  parameters, schemas, request schemas, response schemas, security schemes, and
  explicit `x-nlreq-state-transition` annotations
- actor binding through a single unambiguous security scheme
- ambiguity detection for duplicate operation ids and repeated symbol names
- adapter binding validation against the parsed OpenAPI symbol index
- `STATICALLY_RESOLVED` and `TYPE_CHECKED` evidence capability reporting
- adapter verification tasks for OpenAPI symbol shape, auth rejection
  declarations, and success response declarations
- OpenAPI package generation through `nlreq openapi-package`
- OpenAPI package validation through `nlreq openapi-validate`
- package-index, soft-gate, hard-gate, and CI report validation through
  `--openapi-document`
- adapter conformance coverage through `nlreq openapi-conformance`

## Supported Claim Shapes

Unauthorized actor rejection:

```text
For every operation request:
if actor is not authorized
then operation must be rejected before state_change.
```

The OpenAPI operation must declare:

- an operation id or operation binding matching the controlled action,
- a security requirement that references the bound actor security scheme,
- a `401` or `403` response,
- and `x-nlreq-state-transition: state_change` when the controlled requirement
  uses `rejected before state_change`.

Approved actor success:

```text
For every operation request:
if actor is approved
then operation must succeed.
```

The OpenAPI operation must declare:

- an operation id or operation binding matching the controlled action,
- a security requirement that references the bound actor security scheme,
- and at least one `2xx` response.

## Boundary

OpenAPI evidence is declaration evidence. It may satisfy `STATICALLY_RESOLVED`
or `TYPE_CHECKED`; it does not satisfy `TEST_VALIDATED`, `TRACE_VALIDATED`,
`BOUNDED_CHECKED`, or `PROVEN_INDUCTIVE`.

The adapter does not execute services, prove handler behavior, validate runtime
ordering before state mutation, or claim that an implementation package satisfies
the OpenAPI contract. Cross-adapter requirements remain out of scope.

The YAML loader intentionally supports only the simple mapping/list/scalar subset
used by deterministic OpenAPI fixtures. Anchors, aliases, multiline scalars,
tags, and complex YAML features are unsupported unless a future ADR adds a full
YAML dependency.

## Validation

```bash
uv run pytest tests/test_openapi_adapter.py tests/test_openapi_package.py

uv run nlreq openapi-conformance \
  tests/fixtures/adapters/openapi/sample-openapi.json \
  --openapi-name sample-api

uv run nlreq openapi-package tests/fixtures/requirements/authorization_precondition.nlreq \
  --out /tmp/REQ-OPENAPI-001 \
  --requirement-id REQ-OPENAPI-001 \
  --title "Unauthorized OpenAPI operation is rejected before state changes" \
  --claim-kind authorization_precondition \
  --document tests/fixtures/adapters/openapi/sample-openapi.json \
  --openapi-name sample-api

uv run nlreq openapi-validate /tmp/REQ-OPENAPI-001 \
  --document tests/fixtures/adapters/openapi/sample-openapi.json \
  --openapi-name sample-api
```
