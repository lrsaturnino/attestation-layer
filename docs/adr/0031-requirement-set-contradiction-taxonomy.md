# ADR 0031: Requirement-Set Contradiction Taxonomy

## Status

Accepted (revises the first deterministic slice).

## Context

The self-consistency check detects contradictions inside one flat claim, where every fragment in a
conjunction co-occurs by construction. The roadmap requires detecting contradictions across a
*requirement set*, where co-occurrence is no longer free: two requirements only contradict in a
state their conditions can both reach.

The first slice of this report keyed on `opposite_predicate` — two requirements asserting opposite
predicates over the same arguments, such as `approved(actor)` and `not_approved(actor)`. Applied to
requirement *premises*, that rule is unsound: a rule for the approved case and a rule for the
not-approved case are the two halves of a complete, consistent specification, not a contradiction —
their premises are mutually exclusive, so they never both fire. Pooling premise predicates this way
reported satisfiable sets as contradictory.

## Decision

Decide cross-requirement consistency over the typed `FormalClaim` fragments produced by
`build_formal_claim`, comparing requirement *obligations* — what each requirement must make true —
rather than premises.

Two requirements' obligations are compared only when their premises provably co-occur on a shared
scope: equal premise signatures, including the both-unconditional case. When the premises differ we
cannot prove they ever hold together, so the pair is left unflagged. This conditional-overlap gate
is the soundness boundary; the checker is deliberately conservative because a false positive blocks a
satisfiable set, which is worse than a miss a formal backend can still catch.

Under that gate, three classes are decided deterministically and emitted:

- `numeric_range_disjointness`: invariant bounds on one variable bound an empty interval; only the
  binding lower/upper pair is reported.
- `mutual_exclusion`: two post-state obligations pin one variable to incompatible values.
- `action_order_conflict`: one requirement requires an action to succeed, another to be rejected.

Four further classes are catalogued (`contradiction_taxonomy.build_cross_requirement_contradiction_taxonomy`)
with the reason each is not emitted: `conditional_overlap` is the co-occurrence gate itself rather
than a standalone finding; `negation`, `quantifier_scope_conflict`, and `temporal_conflict` describe
conflicts the current grammar cannot express across requirements (no negatable obligation, a flat
scope with no subsumption, and an upper-bound-only `within`), so there is no real contradiction to
miss. `opposite_predicate` is withdrawn for the reason above.

Each emitted contradiction records its type, the participating requirement ids, the two conflicting
fragments, and their source spans. Source spans are required: a candidate that cannot be tied back
to source text is dropped rather than reported spanless.

## Consequences

Cross-requirement consistency now reports only genuinely jointly-inconsistent obligations, with a
minimal conflicting core tied to source. The tradeoff is limited coverage: conflicts that depend on
non-identical-but-compatible premises, or on grammar the taxonomy cannot express, remain for the
formal backend rather than being approximated by an unsound deterministic rule.
