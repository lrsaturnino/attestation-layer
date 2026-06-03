# Milestone Group 13 Programming-Language Adapter Closure Digest

Milestone group 13 implements phases 138 through 143 from
`docs/conclusion-real-evidence-closure-roadmap.md`. It turns adapter support
from a set of static prototypes into a schema-backed adapter capability and
certification surface that can demonstrate programming-language agnosticism
across transaction/event, compiled service, frontend/service, dynamic scripting,
and compiled systems ecosystems.

## Roadmap Digest

Groups 10 through 12 made translation, formal checking, and brownfield
grounding harder to overclaim. Group 13 closes the next gap:

```text
adapter interface -> capability contract -> ecosystem adapters
-> normalized source and trace evidence -> v2 certification
-> public plugin manifest and validation
```

The release risk is claiming "programming-language agnostic" while only proving
one language shape. This group blocks that risk by making capability claims
machine-readable, forcing unsupported language features into adapter
limitations, preserving ambiguity instead of collapsing it, and certifying
multiple materially different adapters through the same source, trace, and
plugin SDK contracts.

## Phase Map

| Phase | Theme | Primary implementation |
|---:|---|---|
| 138 | Adapter interface v2 | `nlreq.source_adapter.AdapterCapabilityContract` |
| 139 | Solidity graduation | `nlreq.production_source_adapters.SoliditySourceAdapter` |
| 140 | Go graduation | `nlreq.production_source_adapters.GoSourceAdapter` |
| 141 | TypeScript and JavaScript graduation | `TypeScriptSourceAdapter`, `JavaScriptProductionSourceAdapter` |
| 142 | Rust or Java graduation | `RustSourceAdapter`, `JavaSourceAdapter` |
| 143 | Certification and plugin SDK | `nlreq.adapter_certification` plugin models |

## Spec And ADR Matrix

| Phase | Spec | ADR | Primary contracts | Verification surface |
|---:|---|---|---|---|
| 138 | `docs/phase-138-adapter-interface-v2-capability-contract.md` | `docs/adr/0147-adapter-interface-v2-capability-contract.md` | interface v2, capability claims, limitations, evidence labels | `tests/test_milestone_group13.py` |
| 139 | `docs/phase-139-solidity-adapter-graduation.md` | `docs/adr/0148-solidity-adapter-graduation.md` | EVM symbol roles, overload blocking, normalized transaction traces | `tests/test_milestone_group13.py` |
| 140 | `docs/phase-140-go-adapter-graduation.md` | `docs/adr/0149-go-adapter-graduation.md` | package graph metadata, static call graph, Go trace normalization | `tests/test_milestone_group13.py` |
| 141 | `docs/phase-141-typescript-javascript-adapter-graduation.md` | `docs/adr/0150-typescript-javascript-adapter-graduation.md` | TS static fixtures, JS fallback, dynamic-pattern limitations | `tests/test_milestone_group13.py` |
| 142 | `docs/phase-142-rust-or-java-adapter-graduation.md` | `docs/adr/0151-rust-or-java-adapter-graduation.md` | Rust primary pressure test, Java overload ambiguity, compiled ecosystem limits | `tests/test_milestone_group13.py` |
| 143 | `docs/phase-143-adapter-certification-plugin-sdk.md` | `docs/adr/0152-adapter-certification-plugin-sdk.md` | certification fixtures, plugin manifests, plugin validation reports | `tests/test_milestone_group13.py` |

## Implemented Schemas

- `schemas/adapter-capability-contract.schema.json`
- `schemas/adapter-capability-registry.schema.json`
- `schemas/adapter-certification-fixture.schema.json`
- `schemas/adapter-certification-report.schema.json`
- `schemas/adapter-plugin-manifest.schema.json`
- `schemas/adapter-plugin-validation-report.schema.json`

## Shared Contracts

- Adapters expose `interface_version=2.0` capability contracts.
- Capability claims must name the evidence labels they can support.
- `supported_evidence` cannot list evidence that no capability claim backs.
- Required capabilities can be enforced during certification.
- Unsupported, review-only, and blocking limitations are explicit adapter facts.
- Overloaded or duplicate source symbols are ambiguity, not successful
  resolution.
- Runtime traces stay in normalized trace artifacts and never change
  requirement IR semantics.
- Plugin manifests must bind an entry point, capability contract, and at least
  one certification fixture before SDK validation accepts them.

## Exit Readiness

Group 13 exits when specs and ADRs are accepted, schemas are generated,
`tests/test_milestone_group13.py` passes, and the older adapter, schema, and
source conformance tests continue to pass against the v2 certification surface.
