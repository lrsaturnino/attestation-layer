# ADR 0031: Requirement-Set Contradiction Taxonomy

## Status

Accepted (revised — SMT-gated tri-state co-occurrence; fail-closed on undecidable overlap and on
spanless conflicts).

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

Two requirements' obligations are compared only when their premises can both hold — the
conditional-overlap gate, and the soundness boundary, because a false positive blocks a satisfiable
set, which is worse than a miss a formal backend can still catch. Co-occurrence is no longer a
syntactic signature match; it is decided by the satisfiability of the conjunction of both premise
sets (`formal_claim_smt.premises_jointly_satisfiable`), a three-way verdict:

- **Provably co-occur** — the conjunction is satisfiable, so the obligations are compared. This
  clears not only identical premises but overlapping-but-not-identical ones (a bare condition and
  that same condition plus an extra constraint), independent premises that can both hold, and the
  unconditional-vs-conditional case.
- **Provably cannot co-occur** — the conjunction is unsatisfiable, or the premises sit on different
  scopes, so the obligations never both fire and the pair is left unflagged. Opposite predicates
  (`approved` vs `not_approved`) and numerically empty overlaps (`amount >= 10` with `amount <= 5`)
  are declined here.
- **Undecidable here** — a premise has no SMT encoding (an opaque named-set membership) and the
  encoded remainder is satisfiable, so co-occurrence cannot be decided. A conflicting obligation pair
  is surfaced as `premise_overlap_undecidable` and the set is reported `unsupported`, never silently
  passed: an honest "could not decide" must not collapse into acceptance that hides a contradiction.
  Identical premises are the one exception — they trivially co-occur, so an undecidable conjunction
  with equal premise signatures is still sound co-occurrence.

Under that gate, the seven classes the checker reasons about are handled three ways, recorded on each
class's `handling` field (`contradiction_taxonomy.build_cross_requirement_contradiction_taxonomy`) so
a non-emitted class is never mistaken for an unimplemented check:

- **emitted** — decided deterministically over obligation fragments and reported as findings:
  `numeric_range_disjointness` (invariant bounds on one variable bound an empty interval; only the
  binding lower/upper pair is reported), `mutual_exclusion` (two post-state obligations pin one
  variable to incompatible values), and `action_order_conflict` (one requirement requires an action
  to succeed, another to be rejected).
- **gate** — `conditional_overlap` is the co-occurrence precondition above: real, tested SMT logic,
  not a standalone finding.
- **grammar_deferred** — `negation`, `quantifier_scope_conflict`, and `temporal_conflict` describe
  conflicts the v3 grammar cannot express across requirements (no negatable obligation, a flat scope
  with no subsumption, and an upper-bound-only `within`), so there is no real contradiction to miss.
  `temporal_conflict` additionally waits on PA-3's bounded-temporal lowering before a
  cross-requirement temporal bound is representable at all. `opposite_predicate` is withdrawn for the
  reason above.

Each emitted contradiction records its type, the participating requirement ids, the two conflicting
fragments, and their source spans. Source spans are required: a detected conflict whose binding
fragment carries no span is not dropped but surfaced as a `contradiction_without_source_span`
unchecked entry, so the set fails closed rather than silently lose a contradiction it cannot tie to
text.

## Consequences

The set checker reports `contradiction` when at least one proven, source-tied conflict was found
(taking precedence even if some pair was also left undecided); `unsupported` (report schema 0.2, with
an `unchecked` list naming each undecided pair) when no proven conflict but some pair could not be
cleared — a requirement that failed to lower, an undecidable premise overlap, or a conflict with no
source span; and `valid` only when every requirement lowered and every co-occurring obligation pair
cleared. A genuine contradiction carries a minimal conflicting core tied to source. The earlier
tradeoff is narrowed: overlapping-but-not-identical compatible premises are now decided by the SMT
gate rather than deferred to the formal backend, and the residual coverage limit — the
grammar-deferred classes and premises with no SMT encoding — fails closed as `unsupported` instead of
being approximated by an unsound deterministic rule.
