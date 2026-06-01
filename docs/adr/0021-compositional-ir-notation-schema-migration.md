# ADR 0021: Compositional IR Notation, Schema, And Migration

## Status

Proposed

## Context

The current `ir_version: "0.1"` model represents one flat claim:

```text
forall + condition[] + action + expected
```

That shape is deterministic, reviewable, versioned, hashable, and useful for
the Phase-0-plus adapter portfolio. It is also too flat for the next verification
spine. `docs/vision-gap-spec.md` identifies GAP-A3 as the missing
compositional intermediate representation: a structured tree of semantic
scopes, relations, atomic propositions, actions, state, temporal clauses,
numeric/logical constraints, external-context references, provenance, and
confidence markers.

The IR must not become a disguised formal-backend syntax. TLA+, SMT-LIB, LTL,
Alloy, Lean, and future targets need lowering adapters around the IR; they
should not define the IR spine itself.

ADR 0002 requires explicit IR versioning and forbids silent upgrades of reviewed
packages.

## Decision

Phase 19 will introduce a compositional `ir_version: "0.2"` requirement IR.

The authoritative semantic field is `semantic_ir`: a typed JSON tree centered on
the notation:

```text
scope |- premise => obligation
```

Each semantic node has:

- a stable `node_id`;
- a discriminating `kind`;
- source-span or derived-from provenance;
- a confidence marker;
- optional namespaced annotations;
- and typed child fields appropriate to that node kind.

The first node families are:

- rule nodes;
- scope and quantifier nodes;
- logical relation nodes;
- atomic predicate, comparison, membership, and state-reference nodes;
- action, event, call, and transition nodes;
- pre-state, post-state, invariant, and state-delta nodes;
- temporal nodes such as before, within, eventually, always, and until;
- numeric/logical constraint nodes;
- external-context references for system specs, code symbols, traces, and
  policies.

The top-level envelope remains close to the existing package shape:

```text
RequirementIRV2:
  ir_version
  requirement_id
  title
  source
  semantic_ir
  bindings
  assumptions
  required_evidence
```

Existing `0.1` packages remain valid as `0.1` packages. They are never silently
upgraded. New validators must dispatch by `ir_version`.

Migration from `0.1` to `0.2` is deterministic and explicit:

- the migrated artifact records the source IR hash;
- the migration tool version is recorded;
- the migration diff is recorded;
- `forall` becomes scope;
- `condition[]` becomes a premise relation;
- `action` and `expected` become an action obligation;
- existing source spans are preserved;
- unsupported or lossy mappings refuse instead of inventing semantics.

Adapters that still need the flat model may use an in-memory legacy projection
only when the compositional tree is exactly representable as a `0.1` claim. The
projection is not authoritative package content and cannot hide unsupported
structure.

Backend-specific hints live under namespaced `annotations`. Annotations may help
a backend choose names or lowering strategies, but the requirement meaning must
remain in the typed semantic nodes. If required semantics exist only in an
annotation namespace, the backend must refuse.

## Rejected Alternatives

Keep extending the flat `claim` object.

This would preserve short-term adapter compatibility, but it would encode nested
premises, temporal behavior, external system-spec references, and multi-obligation
requirements as ad-hoc optional fields. The result would be flat in name only
and hard to lower consistently.

Make TLA+ or SMT-LIB the canonical IR.

This would accelerate one backend but violate the roadmap invariant that the IR
is the spine and formal systems are adapters around it. It would also make
cross-backend agreement and later agnosticism harder.

Use JSON-LD/RDF as the first canonical representation.

JSON-LD may be useful as an export format later, but it adds vocabulary and graph
machinery before the project has proven the smaller typed-tree contract.

Store only prose decomposition with backend snippets.

That would help humans inspect requirements but would not give validators,
migration tools, or formal backends a deterministic semantic object to consume.

## Consequences

The project gains an IR that can represent real requirements without committing
to a formal backend too early. Phase 20 can design backend lowering against a
stable semantic contract instead of reverse-engineering semantics from flat
claims or backend hints.

The tradeoff is migration and adapter complexity. Existing code that assumes
`RequirementIR.claim` must either remain on `0.1`, consume an exact legacy
projection, or become `0.2`-aware.

`0.2` representation is not stronger evidence. Temporal nodes, external system
references, and multi-premise obligations are representable before they are
checkable. Status and gate logic must continue to treat unsupported, timed-out,
or unchecked semantics as non-approving states.

Explicit version dispatch and migration records preserve auditability. Old
package hashes remain meaningful, and new packages can carry richer structure
without rewriting history.
