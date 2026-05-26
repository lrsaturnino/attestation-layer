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

Phase 5 artifact examples:

- `docs/examples/gate-policy.example.json`
- `docs/examples/waiver.example.json`

Phase 6 artifact schemas:

- `schemas/counterexamples.schema.json`
- `schemas/generated-tests.schema.json`
- `schemas/normalized-traces.schema.json`

Phase 7 adapter fixture:

- `tests/fixtures/adapters/openapi/sample-openapi.json`
