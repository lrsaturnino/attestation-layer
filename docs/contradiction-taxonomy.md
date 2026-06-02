# Contradiction Taxonomy

Phase 54 expands requirement self-consistency from narrow deterministic checks
into a stable taxonomy. The checker remains conservative: unsupported or unknown
classes must not be silently accepted.

| Code | Type | Meaning |
|---|---|---|
| `CONTRADICTION_DIRECT_OPPOSITE_PREDICATES` | `direct_opposite_predicates` | The same condition appears in positive and negative form. |
| `CONTRADICTION_IMPOSSIBLE_COMPARISON` | `impossible_comparison` | A literal comparison is unsatisfiable, such as `5 <= 3`. |
| `CONTRADICTION_MUTUALLY_EXCLUSIVE_STATES` | `mutually_exclusive_states` | State predicates require incompatible values. |
| `CONTRADICTION_OVERLAPPING_OPPOSITE_OBLIGATIONS` | `overlapping_opposite_obligations` | Matching conditions impose opposite obligations. |
| `CONTRADICTION_TEMPORAL_IMPOSSIBILITY` | `temporal_impossibility` | A temporal bound is impossible, such as a negative duration. |
| `CONTRADICTION_NUMERIC_BOUND_CONFLICT` | `numeric_bound_conflict` | Lower and upper bounds for the same value cannot both hold. |
| `CONTRADICTION_DUPLICATE_OBLIGATION_CONFLICT` | `duplicate_obligation_conflict` | The same obligation is duplicated where uniqueness matters. |

Backend counterexamples remain represented as `backend_counterexample` because
the formal backend may detect contradictions outside deterministic coverage.

Every deterministic contradiction includes source spans when the originating IR
node has them. Unknown classes remain `unsupported`, `timeout`, or `tool_error`
according to the formal backend result.
