# ADR 0022: Formal Backend Interface And Lowering Contract

## Status

Proposed

## Context

Phase 19 introduced `ir_version: "0.2"` as the compositional semantic spine.
The next roadmap dependency is GAP-C4: formal-backend adapters that can consume
the IR and eventually lower it to TLA+, SMT-LIB, LTL, Alloy, Lean, or another
formal target.

The project already has two formal-adjacent paths:

- `core_smt`, which checks flat `0.1` claims for limited self-consistency;
- the Phase 13 TLA adapter, which runs reviewed TLA+ models and configs.

Neither is the compositional backend boundary. `core_smt` is flat and narrow;
the TLA adapter executes reviewed models but does not lower the new IR.

The boundary must come before full lowering so the IR does not become a hidden
copy of one backend syntax.

## Decision

Define a formal backend contract around two versioned artifacts:

```text
FormalBackendRequest
FormalBackendResponse
```

A request contains:

- schema version;
- backend id;
- target formalism;
- the `RequirementIRV2` document;
- an entry node id;
- optional execution/lowering budget.

A response contains:

- schema version;
- backend id;
- target formalism;
- normalized `BackendResult`;
- explicit unsupported constructs;
- consumed annotations;
- optional lowered artifact hash.

The first target boundary is TLA+, implemented as `tla-boundary`. It does not
perform full lowering or model checking. It validates the shape that would be
offered to TLA+ lowering, records consumed `tla` annotations, and returns
`unsupported` when semantic nodes are outside the supported boundary.

Backend annotations remain namespaced. A backend may consume only its namespace
and must require `schema_version` on annotations it consumes. The typed semantic
tree remains authoritative; annotations may guide lowering but cannot carry
hidden requirement meaning.

Existing formal paths remain:

- `core_smt` continues to handle flat `0.1` self-consistency;
- the TLA package/check adapter continues to run reviewed TLA+ models;
- future phases may connect compositional lowering to those execution paths.

## Rejected Alternatives

Make the Phase 13 TLA adapter the compositional backend interface.

That adapter is valuable, but it is reviewed-model execution, not an
IR-lowering contract. Reusing it as the boundary would conflate model execution
with semantic lowering.

Lower directly to TLA+ before defining the common response contract.

That would make the first implementation faster, but it would make unsupported
constructs, annotation consumption, timeout semantics, and cross-backend
agreement ad hoc.

Use `core_smt` as the first compositional backend.

`core_smt` is intentionally narrow and flat. It is useful for Phase-0 claims,
but it cannot drive the state/temporal roadmap without forcing the new IR into
propositional shape.

## Consequences

The project gets a stable edge between the compositional IR and future formal
targets. Unsupported constructs become explicit artifacts rather than implicit
backend failures.

The tradeoff is that Phase 20 returns boundary results, not proof. A successful
boundary response can say the shape is acceptable for later lowering, but it
cannot satisfy `BOUNDED_CHECKED` or `PROVEN_INDUCTIVE`.

TLA+ becomes the first formal target boundary, but the IR remains backend
agnostic because target-specific details stay in versioned annotations and are
reported when consumed.
