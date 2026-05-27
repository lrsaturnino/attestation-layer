# Future Adapter Expansion and Routing

This note captures the future adapter strategy for the NL Requirement
Attestation Layer. It is not an implemented Phase 0-9 feature. The current
implementation routes adapters explicitly through CLI commands and validation
configuration.

## Current State

The current implementation supports:

- generic static-symbol packages through `nlreq package`
- Python packages through `nlreq python-package`
- OpenAPI documents through `nlreq openapi-package`
- report and gate validation with optional Python and OpenAPI adapter
  configuration

Adapter selection is operator driven:

```text
operator or CI config
  -> command and adapter options
  -> selected adapter
  -> package/evidence/status artifacts
```

There is no automatic adapter registry or router today.

## Goal

Future adapter routing should let many adapters coexist without making the core
system ecosystem-specific.

The target model is:

```text
reviewed package metadata
  + gate policy
  + changed paths
  + adapter capabilities
  + required evidence
  -> deterministic adapter router
  -> one or more selected adapters
  -> normalized evidence
  -> existing status and gate machinery
```

The router must be deterministic, auditable, and conservative. It should never
guess silently or claim stronger evidence than an adapter actually produced.

## Non-Goals

The adapter strategy should not require one project to implement hundreds of
ecosystem adapters.

It should also not:

- infer trust from file extensions alone;
- treat agent or LLM output as evidence;
- hide unsupported ecosystems behind generic success;
- mutate reviewed requirement packages in place;
- bypass adapter conformance;
- or make `decide_status` depend on external tools, filesystem state, network
  calls, CI context, or side effects.

## Adapter Portfolio Strategy

Adapters should be added by trust-boundary value, not ecosystem count.

High-value adapter families:

| Family | Examples | Purpose |
|---|---|---|
| Protocol/spec adapters | OpenAPI, GraphQL, AsyncAPI, protobuf/gRPC, JSON Schema | Validate API contracts across many implementation languages. |
| Language/runtime adapters | Python, TypeScript, Go, Rust, Solidity | Resolve source symbols and collect target-specific implementation evidence. |
| Test-runner adapters | pytest, Jest/Vitest, `go test`, `cargo test`, Foundry/Hardhat | Reuse existing executable tests as `TEST_VALIDATED` evidence. |
| Trace adapters | OpenTelemetry, structured logs, event streams | Validate observed runtime behavior against requirements or models. |
| Formal/spec adapters | TLA+, Alloy, Dafny, Lean | Produce bounded, model-checked, or proof-backed evidence for critical paths. |
| Infrastructure adapters | Terraform, Kubernetes manifests, policy-as-code | Check deployment and operational requirements. |

Unsupported ecosystems remain explicit. They can be report-only, manually
reviewed, or refused until an adapter can produce honest evidence.

## Routing Inputs

Future routing should prefer reviewed and policy-controlled inputs in this
order:

1. **Reviewed requirement package metadata**
   - The strongest routing source.
   - Declares which target artifacts and adapters are in scope for the
     requirement.

2. **Gate policy**
   - Maps repository paths, package roots, adapters, and minimum evidence levels
     to enforcement behavior.
   - Useful for CI and rollout.

3. **Changed paths**
   - Useful for scoping checks after routing is already constrained by reviewed
     metadata or policy.
   - File patterns alone are not enough to claim semantic coverage.

4. **Adapter capabilities**
   - Used to match required evidence to adapters that can honestly provide it.
   - Example: `TRACE_VALIDATED` requires a trace adapter; `BOUNDED_CHECKED`
     requires a model-checking adapter.

5. **Manual override**
   - Allowed for migration and debugging only when recorded in audit output.

## Package Metadata Shape

A future package may include reviewed target metadata like this:

```json
{
  "targets": [
    {
      "target_id": "api",
      "kind": "openapi",
      "adapter": "openapi",
      "path": "api/openapi.yaml"
    },
    {
      "target_id": "implementation",
      "kind": "python",
      "adapter": "python-package",
      "package_root": "src/payments",
      "project_root": "."
    }
  ]
}
```

For cross-artifact requirements, a package may bind multiple targets:

```json
{
  "targets": [
    {
      "target_id": "contract",
      "kind": "openapi",
      "adapter": "openapi",
      "path": "api/openapi.yaml"
    },
    {
      "target_id": "service",
      "kind": "python",
      "adapter": "python-package",
      "package_root": "src/service"
    },
    {
      "target_id": "runtime",
      "kind": "trace",
      "adapter": "opentelemetry-trace",
      "trace_stream": "payments.production"
    }
  ]
}
```

Cross-target claims should remain report-only until every involved adapter is
independently trustworthy and the relationship between targets has an explicit
evidence contract.

## Adapter Registry

A future registry should record adapter identity, target kind, input contract,
capabilities, and conformance status.

Example shape:

```json
{
  "adapters": [
    {
      "adapter_id": "python-package",
      "target_kind": "python",
      "capabilities": [
        "STATICALLY_RESOLVED",
        "TEST_VALIDATED"
      ],
      "claim_kinds": [
        "authorization_precondition",
        "state_precondition"
      ],
      "conformance": {
        "status": "pass",
        "suite_version": "0.1"
      }
    },
    {
      "adapter_id": "tla",
      "target_kind": "tla_spec",
      "capabilities": [
        "BOUNDED_CHECKED",
        "PROVEN_INDUCTIVE"
      ],
      "claim_kinds": [
        "bounded_temporal",
        "numeric_invariant"
      ],
      "conformance": {
        "status": "pending",
        "suite_version": "0.1"
      }
    }
  ]
}
```

Only adapters with passing conformance should satisfy gates. Pending adapters
may produce report-only findings during rollout.

## Routing Rules

The router should produce one of these decisions for each target:

- `selected`: adapter is selected and allowed to produce gateable evidence.
- `report_only`: adapter can run, but findings cannot satisfy blocking policy.
- `missing_adapter`: package or policy requires an adapter that is unavailable.
- `unsupported_claim`: no adapter can support the requirement claim shape.
- `ambiguous_route`: multiple adapters match and policy does not select one.
- `out_of_scope`: changed paths or policy scope do not require this adapter.

Routing should fail closed for hard gates. An ambiguous or missing adapter is a
blocking condition when policy requires that evidence.

## Example Routing Policy

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
    },
    {
      "name": "python-service",
      "path_patterns": ["src/**/*.py"],
      "target_kind": "python",
      "adapter": "python-package",
      "minimum_evidence": ["TEST_VALIDATED"]
    },
    {
      "name": "critical-state-machine",
      "requirement_id_patterns": ["REQ-CRITICAL-*"],
      "target_kind": "tla_spec",
      "adapter": "tla",
      "minimum_evidence": ["BOUNDED_CHECKED"]
    }
  ]
}
```

This policy should be treated as routing input, not a replacement for reviewed
package metadata.

## C4 Placement

```text
Layer 7: Package and Gate Emission
  emits reports, CI results, PR comments, agent handoffs
  ↑
Layer 6: Status Decision
  pure evidence-to-status function
  ↑
Layer 5: Evidence Aggregator
  normalizes backend results into EvidenceObject
  ↑
Layer 4b: Adapter Router and Registry
  chooses adapters from reviewed metadata, policy, paths, and capabilities
  ↑
Layer 4a: Verification Dispatcher
  creates verification tasks for selected adapters
  ↑
Layer 3: Adapter Interface and Symbol Binding
  ecosystem-specific symbol resolution and evidence collection
  ↑
Layer 2: Requirement IR
  typed, versioned, deterministic requirement representation
  ↑
Layer 1: Controlled Requirement Input
```

The router is below status and gates. It must not change how status is computed;
it only decides which adapters can attempt to produce evidence.

## Implementation Phases

### Step 1: Declare Target Metadata

Add an optional `targets` artifact or field with reviewed adapter target
metadata. Keep existing packages valid.

### Step 2: Add Registry Schema

Define adapter registry JSON and validation rules. Include adapter id, target
kind, capabilities, claim kinds, configuration schema, and conformance status.

### Step 3: Add Router Report

Introduce a report-only command:

```bash
uv run nlreq route-adapters requirements \
  --routing-policy docs/examples/routing-policy.example.json \
  --changed-path src/payments/service.py \
  --out /tmp/nlreq-routing.json
```

The command should explain which adapters would run and why.

### Step 4: Integrate With Package Index

Include routing summaries in package index and CI reports. Keep enforcement
report-only until routing is stable.

### Step 5: Integrate With Soft and Hard Gates

Allow gate policies to require specific adapter evidence for scoped packages and
paths. Missing, ambiguous, or unsupported routes become hard-gate findings only
when policy opts in.

### Step 6: Integrate With Agent Workflow

Add routing decisions to `agent-task` and `agent-verify` payloads so coder and
verifier agents know which target artifacts and adapters are authoritative.

## Safety Requirements

- Every routing decision must include a reason.
- Every selected adapter must record its configuration fingerprint.
- Every gateable adapter must pass conformance.
- Every evidence claim must include target artifact hashes.
- Manual overrides must appear in audit output.
- Missing and ambiguous adapters must be visible findings.
- Cross-target claims must stay report-only until their evidence contract is
  documented.
- Runtime traces must not satisfy `TRACE_VALIDATED` unless an adapter validates
  a normalized trace artifact against a documented contract.
- Model checkers must record checker version, command line, bounds, constants,
  model hash, and counterexamples.

## Success Criteria

The routing layer is ready for enforcement when:

- existing generic, Python, and OpenAPI workflows still validate unchanged;
- at least three adapters can register with capabilities and conformance status;
- routing reports are byte-stable for the same package/policy/path inputs;
- missing, ambiguous, unsupported, report-only, and selected routes have tests;
- hard gates can opt into adapter-specific minimum evidence without changing
  `decide_status`;
- and agent handoff artifacts show selected adapters, target hashes, and retry
  instructions for failed adapter evidence.
