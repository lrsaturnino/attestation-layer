# Phase 20 Formal Backend Boundary

Phase 20 defines how compositional IR enters formal backends without making the
IR itself TLA-shaped, SMT-shaped, or tied to any one prover.

This phase is a boundary phase. It introduces the backend request/response
contract, explicit unsupported-construct reporting, scoped backend annotations,
and the first target boundary. It does not implement full formal lowering.

## Purpose

The phase lets the Attestation Layer say:

```text
This compositional IR document was offered to a named formal backend through a
stable request contract, the backend reported which constructs it supports,
which annotations it consumed, and which constructs it refused.
```

It does not say:

```text
The requirement has been model checked.
The requirement lowered completely to TLA+, SMT-LIB, LTL, Alloy, or Lean.
The backend result is proof evidence.
The checked result is consistent with system spec S.
```

## Why This Comes After Phase 19

Phase 19 made `ir_version: "0.2"` the semantic spine. The next risk is letting a
backend implementation back-propagate its own syntax into that spine. Phase 20
prevents that by defining the backend edge first: inputs are compositional IR
plus scoped annotations; outputs are normalized backend results plus explicit
unsupported constructs.

## Backend Contract

The first contract uses two artifacts:

```text
FormalBackendRequest:
  schema_version
  backend_id
  target
  requirement
  entry_node_id
  budget

FormalBackendResponse:
  schema_version
  backend_id
  target
  result
  unsupported_constructs
  consumed_annotations
  lowered_artifact_hash
```

`result` uses the existing `BackendResult` model. This keeps timeout,
unsupported, invalid, counterexample, and needs-review semantics aligned with
the rest of the system.

## First Target

The first target boundary is TLA+.

This is not yet NL-to-TLA+ generation. The Phase 20 TLA boundary only answers
whether the current compositional tree falls inside the supported lowering
surface and records any TLA annotations it would consume.

The selected first target is TLA+ because:

- Phase 13 already introduced reviewed TLA+ model-checking evidence;
- the remaining roadmap depends on system-level state and temporal reasoning;
- TLA+ is a good first boundary for state machines and temporal clauses;
- and bounded model checking can later be routed through the existing TLA
  adapter without pretending it is inductive proof.

## Unsupported Constructs

Unsupported constructs are first-class output:

```json
{
  "node_id": "obligation.must.within",
  "kind": "within",
  "reason": "node kind is not supported by backend tla-boundary"
}
```

Rules:

- unsupported never approves;
- timeout never approves;
- partial lowering must identify the refused node;
- a backend must not silently ignore nodes it does not understand;
- and unsupported details must be stable enough for a translator or specifier to
  repair the input.

## Annotation Rules

Backend annotations remain optional and namespaced:

```json
{
  "annotations": {
    "tla": {
      "schema_version": "0.1",
      "operator_hint": "FinalizeRedemption"
    }
  }
}
```

Rules:

- annotation namespaces are backend-owned;
- backend-owned annotations must declare `schema_version`;
- consumed annotations are recorded in the response;
- unknown namespaces are ignored by other backends;
- and the typed semantic tree remains the authoritative meaning.

## Relationship To Existing Formal Paths

Existing `core_smt` remains a Phase-0 flat-IR self-consistency check. It is not
the compositional formal backend boundary.

Existing TLA package/check commands remain reviewed-model evidence. They execute
human-reviewed TLA+ modules and configs. Phase 20 does not replace them; it
defines the future IR-to-backend edge that can later dispatch to TLA+ lowering
and then to the Phase 13 execution path.

## CLI Shape

Run the boundary check against a compositional IR:

```bash
uv run nlreq formal-backend-check tests/fixtures/requirements/compositional_ir_v02_multi_premise.json \
  --backend tla-boundary
```

The output is a `FormalBackendResponse` JSON artifact.

## Implementation Scope

Phase 20 implementation should include:

- formal backend request and response models;
- unsupported-construct and consumed-annotation models;
- JSON schemas for the request and response artifacts;
- a `FormalBackend` protocol;
- a TLA boundary backend that accepts `RequirementIRV2`;
- explicit unsupported output for node kinds outside the TLA boundary surface;
- annotation schema-version enforcement for consumed TLA annotations;
- a CLI command that runs the boundary check;
- tests showing supported flat-migrated IR and unsupported richer IR behavior;
- and documentation of how `core_smt` and the Phase 13 TLA adapter relate to the
  new boundary.

## Evidence Semantics

Phase 20 must not produce high-assurance evidence.

- A successful boundary check may return `needs_review` to indicate that the
  backend accepted the shape but did not execute proof or model checking.
- Unsupported constructs return `unsupported`.
- `BOUNDED_CHECKED` still requires a real bounded backend run.
- `PROVEN_INDUCTIVE` still requires a real proof backend.

## Success Criterion

Phase 20 succeeds when:

- the backend interface accepts a compositional IR request;
- the response uses normalized backend result semantics;
- TLA+ is selected as the first target boundary;
- unsupported constructs are explicit and non-approving;
- backend annotations are scoped and versioned;
- existing `core_smt` and TLA package/check paths remain compatible;
- and the boundary does not turn the IR spine into backend syntax.

## Boundary

This phase is not DSL v2, translator implementation, full TLA lowering,
Apalache/TLC execution from compositional IR, system-spec registry, `S ∧ R`
checking, trace alignment, proof-object aggregation, or closure gating.
