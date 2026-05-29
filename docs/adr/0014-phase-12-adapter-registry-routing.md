# ADR 0014: Phase 12 Adapter Registry and Routing

## Status

Proposed

## Context

Phases 0 through 9 built the core requirement-package, evidence, gate,
continuous-attestation, and agent-workflow machinery. Phase 10 is planned to add
a command/test-runner adapter, and Phase 11 is planned to add runtime trace
validation. At that point the system will have multiple practical evidence
sources: generic, Python, OpenAPI, command/test-runner, and trace validation.

The current implementation chooses adapters explicitly through CLI commands and
configuration. That is acceptable while there are few adapters, but it becomes
fragile once multiple adapters can satisfy different evidence levels for the
same requirement or changed path.

The design in `docs/future-adapter-routing.md` already defines the required
direction: reviewed package metadata, gate policy, changed paths, adapter
capabilities, and required evidence should feed a deterministic router. Phase 12
should turn that architectural note into a planned implementation slice.

## Decision

Phase 12 will introduce an adapter registry and deterministic routing layer.

The router will not execute adapters by itself. It will decide which adapters
are selected, report-only, missing, ambiguous, unsupported, or out of scope for
a given package set, routing policy, changed-path set, and required evidence
configuration.

The registry will describe:

- adapter id,
- target kind,
- supported claim kinds,
- supported evidence levels,
- configuration schema,
- conformance status,
- report-only or gateable status,
- and rollout metadata.

Requirement packages may add optional reviewed target metadata. Existing
packages must remain valid without this metadata.

The routing layer will produce route reports that include:

- routing input hashes,
- package ids,
- target metadata,
- selected adapters,
- routing decisions,
- decision reasons,
- missing or ambiguous adapter findings,
- unsupported claim findings,
- evidence levels requested,
- and adapter configuration fingerprints.

The router must not:

- change `decide_status`,
- execute external commands,
- claim evidence,
- infer semantic coverage from file extensions alone,
- silently choose between ambiguous adapters,
- or make unsupported ecosystems look accepted.

## Routing Decision States

The router will use these states:

- `selected`: adapter is selected and allowed to produce evidence.
- `report_only`: adapter can run, but results cannot satisfy blocking policy.
- `missing_adapter`: metadata or policy requires an unavailable adapter.
- `unsupported_claim`: no registered adapter supports the claim shape.
- `ambiguous_route`: multiple adapters match and policy does not select one.
- `out_of_scope`: current policy and changed paths do not require this adapter.

Hard gates may later treat `missing_adapter`, `unsupported_claim`, or
`ambiguous_route` as blocking only when policy opts in.

## Planned Artifacts

Adapter registry example:

```json
{
  "registry_version": "0.1",
  "adapters": [
    {
      "adapter_id": "python-package",
      "target_kind": "python",
      "supported_claim_kinds": [
        "authorization_precondition",
        "state_precondition"
      ],
      "supported_evidence": [
        "STATICALLY_RESOLVED",
        "TEST_VALIDATED"
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

Routing policy example:

```json
{
  "routing_version": "0.1",
  "rules": [
    {
      "name": "python-service",
      "path_patterns": ["src/**/*.py"],
      "target_kind": "python",
      "adapter": "python-package",
      "minimum_evidence": ["TEST_VALIDATED"]
    },
    {
      "name": "runtime-traces",
      "requirement_id_patterns": ["REQ-RUNTIME-*"],
      "target_kind": "trace",
      "adapter": "trace",
      "minimum_evidence": ["TRACE_VALIDATED"]
    }
  ]
}
```

Route report example:

```json
{
  "report_version": "0.1",
  "mode": "adapter_routing",
  "result": "report_only",
  "summary": {
    "packages": 2,
    "selected": 2,
    "report_only": 1,
    "missing_adapter": 0,
    "ambiguous_route": 0,
    "unsupported_claim": 0
  },
  "routes": [
    {
      "requirement_id": "REQ-AUTH-001",
      "target_kind": "python",
      "adapter": "python-package",
      "decision": "selected",
      "reason": "routing policy python-service matched changed path src/auth.py",
      "minimum_evidence": ["TEST_VALIDATED"]
    }
  ]
}
```

## Consequences

Phase 12 makes the system safer as adapter count grows. Users can understand
which adapter was selected, why it was selected, and whether its evidence is
gateable or report-only.

The tradeoff is additional configuration. That is acceptable because routing is
a trust decision. The configuration should be reviewed, versioned, and visible
in reports rather than hidden in CI scripts or agent prompts.

Phase 12 is based directly on `docs/future-adapter-routing.md`. That document
remains the broader architectural note; this ADR defines the concrete planned
phase that should implement the first version.
