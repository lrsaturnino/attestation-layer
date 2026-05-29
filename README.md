# The Attestation Layer

**Architecture specification for spec-mediated verification of agent-produced software.**

> Review the spec, not the code. Verify the code against the spec, not against human intuition. Make the spec small enough to review, formal enough to check, and expressive enough to capture what matters. Treat code as a disposable compilation artifact derived from specs, regenerated on demand, trusted only because the specs are trusted.

This repository holds the **yellow paper** specifying the transitional architecture of the Attestation Layer: the architecture operators should build over the 2026–2030 window, before the human chokepoint at specification review dissolves into exception handling and the closed-loop steady state (described in the Wanabai white paper) becomes achievable.

The full specification is in [**YELLOW_PAPER.md**](./YELLOW_PAPER.md).

## What problem this addresses

When agent fleets drive the marginal cost of software production toward zero, the bottleneck moves from producing software to knowing it is correct. The yellow paper specifies the shape of the infrastructure that closes that gap:

- **The specification artifact** as the non-stochastic anchor — above it, inference is stochastic (LLM-generated); below it, verification is deterministic (tool-checked). The human reviews the spec, not the code.
- **Five specification tiers** — from property-based tests (Tier 1) through contracts, TLA+ model checking, verification-aware intermediate languages (Dafny, Lean 4), to runtime trace verification.
- **A two-agent topology** — specifier and verifier — integrated into an orchestration DAG with a single human review point.
- **An explicit migration path** to the closed-loop steady state described in the companion Wanabai white paper.

## Companion series

| # | Piece | Audience | Link |
|---|------|----------|------|
| 1 | *Out of the Loop* | CTOs, investors, strategists | [Substack](https://saturnino.substack.com/p/out-of-the-loop) |
| 2 | *The Attestation Layer* (article) | Senior engineers, architects | [Substack](https://saturnino.substack.com/p/the-attestation-layer) |
| 3 | *Software as Electricity* | Engineering leadership, futurists | [Substack](https://saturnino.substack.com/p/software-as-electricity) |
| 4 | **Yellow paper** (this repo) | Practicing implementers, formal-methods community | [YELLOW_PAPER.md](./YELLOW_PAPER.md) |
| 5 | *Wanabai* white paper | Builders, VCs, collaborators | [github.com/wanabai/wanabai](https://github.com/wanabai/wanabai) |

## Reference implementation

This repository now includes the Phase 0 core for a general-purpose NL Requirement Attestation Layer under `src/nlreq`.

The Phase 0 implementation is adapter-neutral. It provides:

- controlled-language parsing,
- typed IR and generated JSON Schemas,
- source-span provenance,
- a generic static-symbol adapter,
- an executable adapter conformance suite,
- evidence/status objects,
- Z3-backed Phase 0 SMT checks,
- package generation,
- and a CLI.

Install and test with `uv`:

```bash
uv sync --extra dev
uv run python scripts/check_schema_drift.py
uv run pytest
uv run nlreq validate-all requirements
```

Parse a controlled requirement:

```bash
uv run nlreq parse tests/fixtures/requirements/authorization_precondition.nlreq
```

Build and validate a package:

```bash
uv run nlreq package tests/fixtures/requirements/authorization_precondition.nlreq \
  --out requirements/REQ-AUTH-001 \
  --requirement-id REQ-AUTH-001 \
  --title "Unauthorized operation is rejected before state changes" \
  --claim-kind authorization_precondition

uv run nlreq validate requirements/REQ-AUTH-001
```

Validate every committed example package:

```bash
uv run nlreq validate-all requirements
```

Run adapter conformance against the Phase 0 generic adapter:

```bash
uv run nlreq conformance
```

Run adapter conformance against the Phase 1 Python package adapter:

```bash
uv run nlreq python-conformance tests/fixtures/adapters/pythonpkg/samplepkg --package-name samplepkg
```

Run adapter conformance against the Phase 7 OpenAPI adapter:

```bash
uv run nlreq openapi-conformance tests/fixtures/adapters/openapi/sample-openapi.json \
  --openapi-name sample-api
```

Run adapter conformance against the Phase 14 GraphQL adapter:

```bash
uv run nlreq graphql-conformance tests/fixtures/adapters/graphql/sample-schema.graphql \
  --graphql-name sample-graphql
```

Run adapter conformance against the Phase 15 JSON Schema adapter:

```bash
uv run nlreq json-schema-conformance tests/fixtures/adapters/jsonschema/sample-schema.json \
  --json-schema-name sample-json-schema
```

Run adapter conformance against the Phase 16 AsyncAPI adapter:

```bash
uv run nlreq asyncapi-conformance tests/fixtures/adapters/asyncapi/sample-asyncapi.json \
  --asyncapi-name sample-event-api
```

Build and validate a Python-adapter evidence package:

```bash
uv run nlreq python-package tests/fixtures/requirements/python_operation_success.nlreq \
  --out /tmp/REQ-PY-001 \
  --requirement-id REQ-PY-001 \
  --title "Python operation succeeds for approved actor" \
  --claim-kind state_precondition \
  --package-root tests/fixtures/adapters/pythonpkg/samplepkg \
  --package-name samplepkg \
  --project-root . \
  --test-path tests/fixtures/adapters/pythonpkg

uv run nlreq python-package tests/fixtures/requirements/python_operation_success.nlreq \
  --out /tmp/REQ-PY-PROP-001 \
  --requirement-id REQ-PY-PROP-001 \
  --title "Python operation succeeds for approved actor" \
  --claim-kind state_precondition \
  --package-root tests/fixtures/adapters/pythonpkg/samplepkg \
  --package-name samplepkg \
  --project-root . \
  --property-checks

uv run nlreq python-validate /tmp/REQ-PY-001 \
  --package-root tests/fixtures/adapters/pythonpkg/samplepkg \
  --package-name samplepkg \
  --project-root . \
  --test-path tests/fixtures/adapters/pythonpkg
```

Build and validate an OpenAPI-adapter evidence package:

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

Build and validate a GraphQL-adapter evidence package:

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

Build and validate a JSON Schema-adapter evidence package:

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

Build and validate an AsyncAPI-adapter evidence package:

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

Build and validate a command/test-runner-backed evidence package:

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

uv run nlreq command-evidence requirements \
  --checks docs/examples/command-checks.example.json \
  --requirement-id REQ-AUTH-001 \
  --project-root tests/fixtures/adapters/command \
  --out /tmp/nlreq-command-results.json
```

Build Phase 3 adoption artifacts:

```bash
uv run nlreq package-index requirements --out requirements/index.json

uv run nlreq package-index requirements \
  --openapi-document tests/fixtures/adapters/openapi/sample-openapi.json \
  --openapi-name sample-api

uv run nlreq ci-report requirements \
  --out /tmp/nlreq-ci-report.json \
  --markdown-out /tmp/nlreq-ci-report.md

uv run nlreq review-template REQ-AUTH-001
```

Run the Phase 4 soft gate:

```bash
uv run nlreq soft-gate requirements --requirement-id REQ-AUTH-001

uv run nlreq soft-gate requirements \
  --references-file /tmp/pr-body.md \
  --out /tmp/nlreq-soft-gate.json \
  --markdown-out /tmp/nlreq-soft-gate.md \
  --fail-on-blocking
```

Run the Phase 5 hard gate:

```bash
uv run nlreq hard-gate requirements \
  --policy docs/examples/gate-policy.example.json \
  --requirement-id REQ-AUTH-001 \
  --changed-path src/auth.py

uv run nlreq hard-gate requirements \
  --policy docs/examples/gate-policy.example.json \
  --requirement-id REQ-REFUSED-UNBOUND-001 \
  --changed-path src/auth.py
```

The refused-package hard-gate command is expected to exit non-zero.

Run a Phase 8 continuous attestation report:

```bash
uv run nlreq continuous-attestation requirements \
  --trigger schedule \
  --out /tmp/nlreq-continuous.json \
  --markdown-out /tmp/nlreq-continuous.md
```

Validate normalized runtime traces:

```bash
uv run nlreq trace-validate requirements \
  --requirement-id REQ-AUTH-001 \
  --trace-artifact /tmp/normalized-traces.json \
  --out /tmp/nlreq-trace-validation.json \
  --markdown-out /tmp/nlreq-trace-validation.md

uv run nlreq continuous-attestation requirements \
  --trigger schedule \
  --trace-artifact /tmp/normalized-traces.json \
  --trace-validation \
  --out /tmp/nlreq-continuous-with-traces.json
```

Build an adapter routing report:

```bash
uv run nlreq validate-adapter-registry docs/examples/adapter-registry.example.json
uv run nlreq validate-routing-policy docs/examples/routing-policy.example.json

uv run nlreq route-adapters requirements \
  --adapter-registry docs/examples/adapter-registry.example.json \
  --routing-policy docs/examples/routing-policy.example.json \
  --changed-path src/auth.py \
  --requirement-id REQ-AUTH-001 \
  --out /tmp/nlreq-routing.json \
  --markdown-out /tmp/nlreq-routing.md
```

Build and validate a TLA/model-checking-backed package:

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

uv run nlreq tla-check requirements \
  --model-config docs/examples/tla-models.example.json \
  --requirement-id REQ-AUTH-001 \
  --project-root tests/fixtures/adapters/tla \
  --out /tmp/nlreq-tla-results.json
```

Build a Phase 9 agent verifier handoff:

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

Expected validation output:

```text
Requirement: REQ-AUTH-001
IR: valid
Bindings: valid
Consistency: checked
SMT: checked
Status: ACCEPTED_WITH_EVIDENCE
```

Example packages live under `requirements/`.

The Phase 0 completion record is in [docs/phase-0-completion.md](./docs/phase-0-completion.md).
The Phase 1 Python adapter slice is described in
[docs/phase-1-python-adapter.md](./docs/phase-1-python-adapter.md).
The Phase 2 Python evidence package slice is described in
[docs/phase-2-python-evidence.md](./docs/phase-2-python-evidence.md).
The Phase 3 adoption workflow slice is described in
[docs/phase-3-adoption-workflow.md](./docs/phase-3-adoption-workflow.md).
The Phase 4 soft gate pilot is described in
[docs/phase-4-soft-gate-pilot.md](./docs/phase-4-soft-gate-pilot.md).
The formal roadmap in [docs/build-plan.md](./docs/build-plan.md) now extends
through Phase 16.
The Phase 5 hard gate is described in
[docs/phase-5-hard-gate.md](./docs/phase-5-hard-gate.md).
The Phase 6 stronger evidence backend slice is described in
[docs/phase-6-stronger-backends.md](./docs/phase-6-stronger-backends.md).
The Phase 7 OpenAPI adapter expansion is described in
[docs/phase-7-openapi-adapter.md](./docs/phase-7-openapi-adapter.md).
The Phase 8 continuous attestation slice is described in
[docs/phase-8-continuous-attestation.md](./docs/phase-8-continuous-attestation.md).
The Phase 9 agent workflow integration slice is described in
[docs/phase-9-agent-workflow.md](./docs/phase-9-agent-workflow.md).
The Phase 10 command/test-runner adapter slice is described in
[docs/phase-10-command-test-runner-adapter.md](./docs/phase-10-command-test-runner-adapter.md).
The Phase 11 runtime trace validation slice is described in
[docs/phase-11-runtime-trace-validation.md](./docs/phase-11-runtime-trace-validation.md).
The Phase 12 adapter registry and routing slice is described in
[docs/phase-12-adapter-registry-routing.md](./docs/phase-12-adapter-registry-routing.md).
The Phase 13 TLA+ model-checking adapter slice is described in
[docs/phase-13-tla-model-checking-adapter.md](./docs/phase-13-tla-model-checking-adapter.md).
The Phase 14 GraphQL schema adapter slice is described in
[docs/phase-14-graphql-schema-adapter.md](./docs/phase-14-graphql-schema-adapter.md).
The Phase 15 JSON Schema adapter slice is described in
[docs/phase-15-json-schema-adapter.md](./docs/phase-15-json-schema-adapter.md).
The Phase 16 AsyncAPI adapter slice is described in
[docs/phase-16-asyncapi-adapter.md](./docs/phase-16-asyncapi-adapter.md).

Adoption references:

- [Adapter authoring guide](./docs/adapter-authoring-guide.md)
- [Adding a requirement](./docs/adding-a-requirement.md)
- [Attestation artifact catalog](./docs/attestation-artifact-catalog.md)
- [Future adapter expansion and routing](./docs/future-adapter-routing.md)
- [Review checklist template](./docs/review-checklist-template.md)
- [Examples](./docs/examples.md)

## License

Apache License 2.0. See [LICENSE](./LICENSE) and [NOTICE](./NOTICE).

## Author

Leonardo Saturnino — lrsaturnino@gmail.com — [@Lrsaturnino](https://x.com/Lrsaturnino) — [github.com/lrsaturnino](https://github.com/lrsaturnino)
