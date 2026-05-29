# Examples

Committed requirement packages live under `requirements/`.

| Requirement | Claim Kind | Status | Purpose |
|---|---|---|---|
| `REQ-AUTH-001` | `authorization_precondition` | `ACCEPTED_WITH_EVIDENCE` | Unauthorized operation is rejected before state changes. |
| `REQ-STATE-001` | `state_postcondition` | `ACCEPTED_WITH_EVIDENCE` | Approved operation sets accepted status. |
| `REQ-NUM-001` | `numeric_invariant` | `ACCEPTED_WITH_EVIDENCE` | Counter increments within limit. |
| `REQ-REFUSED-UNBOUND-001` | `authorization_precondition` | `REFUSED_UNBOUND_SYMBOLS` | Negative fixture for refusal provenance. |

Validate all committed examples:

```bash
uv run nlreq validate-all requirements
```

Build an adoption index:

```bash
uv run nlreq package-index requirements
```

Build a shadow CI report:

```bash
uv run nlreq ci-report requirements
```

Run the soft gate against an accepted package:

```bash
uv run nlreq soft-gate requirements --requirement-id REQ-AUTH-001
```

Run the soft gate against the refused negative fixture:

```bash
uv run nlreq soft-gate requirements --requirement-id REQ-REFUSED-UNBOUND-001
```

Run the hard gate against an accepted package:

```bash
uv run nlreq hard-gate requirements \
  --policy docs/examples/gate-policy.example.json \
  --requirement-id REQ-AUTH-001 \
  --changed-path src/auth.py
```

Run the hard gate against the refused negative fixture:

```bash
uv run nlreq hard-gate requirements \
  --policy docs/examples/gate-policy.example.json \
  --requirement-id REQ-REFUSED-UNBOUND-001 \
  --changed-path src/auth.py
```

The refused-package hard-gate command is expected to exit non-zero.

Run a continuous attestation report:

```bash
uv run nlreq continuous-attestation requirements \
  --trigger schedule \
  --out /tmp/nlreq-continuous.json \
  --markdown-out /tmp/nlreq-continuous.md
```

Run trace validation over normalized runtime traces:

```bash
uv run nlreq trace-validate requirements \
  --requirement-id REQ-AUTH-001 \
  --trace-artifact /tmp/normalized-traces.json \
  --out /tmp/nlreq-trace-validation.json \
  --markdown-out /tmp/nlreq-trace-validation.md
```

Build an adapter routing report:

```bash
uv run nlreq route-adapters requirements \
  --adapter-registry docs/examples/adapter-registry.example.json \
  --routing-policy docs/examples/routing-policy.example.json \
  --changed-path src/auth.py \
  --requirement-id REQ-AUTH-001 \
  --out /tmp/nlreq-routing.json \
  --markdown-out /tmp/nlreq-routing.md
```

Build a TLA/model-checking package:

```bash
uv run nlreq tla-package tests/fixtures/requirements/authorization_precondition.nlreq \
  --out /tmp/REQ-AUTH-TLA-001 \
  --requirement-id REQ-AUTH-TLA-001 \
  --title "Unauthorized operation is rejected before state changes" \
  --claim-kind authorization_precondition \
  --model-config docs/examples/tla-models.example.json \
  --project-root tests/fixtures/adapters/tla

uv run nlreq tla-validate /tmp/REQ-AUTH-TLA-001 \
  --model-config docs/examples/tla-models.example.json \
  --project-root tests/fixtures/adapters/tla
```

Build an agent implementation task and verifier handoff:

```bash
uv run nlreq agent-task requirements \
  --requirement-id REQ-AUTH-001 \
  --allowed-path src/auth.py \
  --out /tmp/nlreq-agent-task.json

uv run nlreq agent-verify requirements \
  --requirement-id REQ-AUTH-001 \
  --out /tmp/nlreq-agent-handoff.json \
  --markdown-out /tmp/nlreq-agent-handoff.md
```

Build a Python package with generated property evidence:

```bash
uv run nlreq python-package tests/fixtures/requirements/python_operation_success.nlreq \
  --out /tmp/REQ-PY-PROP-001 \
  --requirement-id REQ-PY-PROP-001 \
  --title "Python operation succeeds for approved actor" \
  --claim-kind state_precondition \
  --package-root tests/fixtures/adapters/pythonpkg/samplepkg \
  --package-name samplepkg \
  --project-root . \
  --property-checks
```

Build an OpenAPI package with declaration-level evidence:

```bash
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

Build a GraphQL package with declaration-level evidence:

```bash
uv run nlreq graphql-package tests/fixtures/requirements/authorization_precondition.nlreq \
  --out /tmp/REQ-GRAPHQL-001 \
  --requirement-id REQ-GRAPHQL-001 \
  --title "Unauthorized GraphQL operation is rejected before state changes" \
  --claim-kind authorization_precondition \
  --schema tests/fixtures/adapters/graphql/sample-schema.graphql \
  --graphql-name sample-graphql

uv run nlreq graphql-validate /tmp/REQ-GRAPHQL-001 \
  --schema tests/fixtures/adapters/graphql/sample-schema.graphql \
  --graphql-name sample-graphql
```

Build a JSON Schema package with declaration-level evidence:

```bash
uv run nlreq json-schema-package tests/fixtures/requirements/state_postcondition.nlreq \
  --out /tmp/REQ-JSON-SCHEMA-001 \
  --requirement-id REQ-JSON-SCHEMA-001 \
  --title "Approved operation sets accepted status" \
  --claim-kind state_postcondition \
  --schema tests/fixtures/adapters/jsonschema/sample-schema.json \
  --json-schema-name sample-json-schema

uv run nlreq json-schema-validate /tmp/REQ-JSON-SCHEMA-001 \
  --schema tests/fixtures/adapters/jsonschema/sample-schema.json \
  --json-schema-name sample-json-schema
```

Build an AsyncAPI package with declaration-level evidence:

```bash
uv run nlreq asyncapi-package tests/fixtures/requirements/event_emit.nlreq \
  --out /tmp/REQ-ASYNCAPI-001 \
  --requirement-id REQ-ASYNCAPI-001 \
  --title "Approved operation emits accepted event" \
  --claim-kind event_state_correspondence \
  --document tests/fixtures/adapters/asyncapi/sample-asyncapi.json \
  --asyncapi-name sample-event-api

uv run nlreq asyncapi-validate /tmp/REQ-ASYNCAPI-001 \
  --document tests/fixtures/adapters/asyncapi/sample-asyncapi.json \
  --asyncapi-name sample-event-api
```

Build a Protobuf/gRPC package with declaration-level evidence:

```bash
uv run nlreq protobuf-package tests/fixtures/requirements/authorization_precondition.nlreq \
  --out /tmp/REQ-PROTOBUF-001 \
  --requirement-id REQ-PROTOBUF-001 \
  --title "Unauthorized gRPC operation is rejected before state changes" \
  --claim-kind authorization_precondition \
  --schema tests/fixtures/adapters/protobuf/sample.proto \
  --protobuf-name sample-protobuf

uv run nlreq protobuf-validate /tmp/REQ-PROTOBUF-001 \
  --schema tests/fixtures/adapters/protobuf/sample.proto \
  --protobuf-name sample-protobuf
```

Build a command/test-runner package with reviewed command evidence:

```bash
uv run nlreq command-package tests/fixtures/requirements/authorization_precondition.nlreq \
  --out /tmp/REQ-CMD-001 \
  --requirement-id REQ-CMD-001 \
  --title "Unauthorized operation is rejected by an existing command check" \
  --claim-kind authorization_precondition \
  --checks docs/examples/command-checks.example.json \
  --project-root tests/fixtures/adapters/command

uv run nlreq command-validate /tmp/REQ-CMD-001 \
  --checks docs/examples/command-checks.example.json \
  --project-root tests/fixtures/adapters/command
```

Phase 5 artifact examples:

- `docs/examples/gate-policy.example.json`
- `docs/examples/waiver.example.json`
- `docs/examples/command-checks.example.json`
- `docs/examples/adapter-registry.example.json`
- `docs/examples/routing-policy.example.json`
- `docs/examples/tla-models.example.json`

Phase 6 artifact schemas:

- `schemas/counterexamples.schema.json`
- `schemas/generated-tests.schema.json`
- `schemas/normalized-traces.schema.json`

Phase 7 adapter fixture:

- `tests/fixtures/adapters/openapi/sample-openapi.json`

Phase 14 and 15 adapter fixtures:

- `tests/fixtures/adapters/graphql/sample-schema.graphql`
- `tests/fixtures/adapters/jsonschema/sample-schema.json`

Phase 16 adapter fixture:

- `tests/fixtures/adapters/asyncapi/sample-asyncapi.json`

Phase 17 adapter fixture:

- `tests/fixtures/adapters/protobuf/sample.proto`
