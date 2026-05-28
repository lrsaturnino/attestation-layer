# Phase 12 Adapter Registry and Routing

Phase 12 should implement the first deterministic adapter registry and routing
layer described in `docs/future-adapter-routing.md`.

This phase is implemented in the reference CLI as `validate-adapter-registry`,
`validate-routing-policy`, and `route-adapters`.

## Purpose

By Phase 12, the project should have enough adapter families that manual routing
through separate CLI commands and ad hoc CI config becomes hard to reason about.

The phase should answer:

```text
For this requirement package,
this changed file set,
this routing policy,
and these required evidence levels,
which adapter should run and why?
```

It should not execute adapters or compute status. It should produce a
deterministic routing report that downstream package, gate, continuous, and
agent workflows can consume.

## Source Design

This phase is based on:

- `docs/future-adapter-routing.md`
- `docs/adr/0014-phase-12-adapter-registry-routing.md`

The future-routing note remains the broader strategy. Phase 12 is the concrete
implementation slice for registry and routing.

## Planned CLI Shape

Example route report:

```bash
uv run nlreq route-adapters requirements \
  --adapter-registry docs/examples/adapter-registry.example.json \
  --routing-policy docs/examples/routing-policy.example.json \
  --changed-path src/payments/service.py \
  --requirement-id REQ-AUTH-001 \
  --out /tmp/nlreq-routing.json \
  --markdown-out /tmp/nlreq-routing.md
```

Example route validation:

```bash
uv run nlreq validate-adapter-registry docs/examples/adapter-registry.example.json

uv run nlreq validate-routing-policy docs/examples/routing-policy.example.json
```

Routing is explicit and reproducible: registry and policy files are validated
separately, and route reports record input hashes when file paths are provided.

## Planned Inputs

### Adapter Registry

The registry records available adapters and whether they can satisfy gates.

```json
{
  "registry_version": "0.1",
  "adapters": [
    {
      "adapter_id": "openapi",
      "target_kind": "openapi",
      "supported_claim_kinds": [
        "authorization_precondition",
        "state_precondition"
      ],
      "supported_evidence": [
        "STATICALLY_RESOLVED"
      ],
      "conformance": {
        "status": "pass",
        "suite_version": "0.1"
      },
      "gateable": true
    }
  ]
}
```

### Routing Policy

The routing policy maps requirements, targets, paths, and evidence expectations
to adapters.

```json
{
  "routing_version": "0.1",
  "rules": [
    {
      "name": "api-contracts",
      "path_patterns": ["api/**/*.yaml", "api/**/*.json"],
      "target_kind": "openapi",
      "adapter": "openapi",
      "minimum_evidence": ["STATICALLY_RESOLVED"]
    }
  ]
}
```

### Reviewed Target Metadata

Future packages may add optional target metadata:

```json
{
  "targets": [
    {
      "target_id": "service",
      "kind": "python",
      "adapter": "python-package",
      "package_root": "src/service"
    }
  ]
}
```

Existing packages must remain valid without this field.

## Routing Decisions

The route report should classify each route as:

| Decision | Meaning |
|---|---|
| `selected` | Adapter is selected and allowed to produce evidence. |
| `report_only` | Adapter can run, but results cannot satisfy blocking policy. |
| `missing_adapter` | Metadata or policy requires an unavailable adapter. |
| `unsupported_claim` | No registered adapter supports the requirement claim shape. |
| `ambiguous_route` | Multiple adapters match and policy does not select one. |
| `out_of_scope` | Current policy and changed paths do not require this adapter. |

Every decision must include a reason.

## Planned Output

```json
{
  "report_version": "0.1",
  "mode": "adapter_routing",
  "result": "report_only",
  "inputs": {
    "packages_root": "requirements",
    "adapter_registry_hash": "sha256:...",
    "routing_policy_hash": "sha256:..."
  },
  "summary": {
    "packages": 1,
    "selected": 1,
    "report_only": 0,
    "missing_adapter": 0,
    "ambiguous_route": 0,
    "unsupported_claim": 0,
    "out_of_scope": 0
  },
  "routes": [
    {
      "requirement_id": "REQ-AUTH-001",
      "target_kind": "python",
      "adapter": "python-package",
      "decision": "selected",
      "reason": "reviewed target metadata selected python-package",
      "minimum_evidence": ["TEST_VALIDATED"],
      "gateable": true
    }
  ],
  "findings": []
}
```

## Integration Points

Phase 12 should integrate routing summaries into:

- package index reports,
- CI reports,
- soft-gate reports,
- hard-gate findings,
- continuous-attestation runs,
- agent implementation tasks,
- agent verifier handoffs,
- and future adapter execution workflows.

Initial integration may be report-only. Hard-gate enforcement should opt in
after routing reports are stable and reviewed.

## Safety Rules

- Routing must not execute external tools.
- Routing must not compute status.
- Routing must not claim evidence.
- Ambiguous routes must be findings, not silent choices.
- Missing adapters must be visible.
- Unsupported claim shapes must stay explicit.
- File path patterns alone must not imply semantic coverage.
- Manual overrides must be recorded in reports and audit output.
- Existing packages must remain valid.
- `decide_status` must remain pure.

## Success Criterion

Phase 12 succeeds when:

- adapter registry and routing policy schemas exist;
- registry and policy validators exist;
- `route-adapters` emits deterministic JSON and Markdown reports;
- route reports cover selected, report-only, missing, ambiguous, unsupported,
  and out-of-scope decisions;
- routing summaries appear in package index, gates, continuous attestation, and
  agent handoffs;
- hard gates can opt into routing findings without changing `decide_status`;
- and existing generic, Python, OpenAPI, command/test-runner, and trace
  workflows remain compatible.

## Boundary

Phase 12 is routing infrastructure, not another evidence backend. It makes
adapter selection auditable before adding more specialized adapters such as
TLA+, GraphQL, Solidity, or Terraform.
