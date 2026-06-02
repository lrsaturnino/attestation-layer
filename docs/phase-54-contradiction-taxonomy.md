# Phase 54 Contradiction Taxonomy

Phase 54 makes self-consistency a first-class requirement analysis backend.

## Taxonomy

The taxonomy is documented in `docs/contradiction-taxonomy.md` and
implemented in `src/nlreq/requirement_self_consistency.py`.

## Deterministic Checks

The checker handles direct opposite predicates, impossible literal
comparisons, numeric bound conflicts, duplicate obligation conflicts, temporal
impossibility, state conflicts, and overlapping opposite obligations where the
IR exposes enough structure.

Direct opposite predicates include controlled DSL pairs such as `authorized`
and `not_authorized`, or `approved` and `not_approved`. Numeric bounds classify
both crossing bounds and equal strict/inclusive conflicts, such as `x > 10`
combined with `x <= 10`.

Formal backend counterexamples remain part of the result when deterministic
checks do not decide the case.

## CLI

```bash
uv run nlreq requirement-self-consistency --requirement-ir requirement.ir.json
```

## Invariants

- Contradictions carry stable codes.
- Source spans are included where available.
- Unknown classes are not silently accepted.
- Backend timeout and tool error never approve a requirement.

## Exit Criteria

The self-consistency report classifies deterministic contradictions and keeps
backend outcomes explicit.

## Implementation Spec

Input artifacts:

- One `RequirementIRV2` requirement checked before composition with system spec
  `S`.
- Optional formal backend budget and execution metadata.

Output artifacts:

- `RequirementSelfConsistencyResult` with status, backend result,
  contradictions, unsupported constructs, and optional backend response.
- `RequirementSelfContradiction` records stable type, code, node IDs, message,
  and source spans when available.

Deterministic taxonomy:

- Direct opposite predicates.
- Impossible numeric comparisons.
- Mutually exclusive state fragments.
- Overlapping opposite obligations.
- Temporal impossibility.
- Numeric bound conflict.
- Duplicate obligation conflict.

Backend behavior:

- Deterministic contradictions short-circuit backend execution.
- If deterministic checks do not decide the case, the formal backend boundary
  runs with explicit unsupported, timeout, and tool-error outcomes.
- Backend counterexamples become contradiction records rather than proof
  closure.

Failure modes:

- Unsupported backend fragments return `unsupported`.
- Timeout returns `timeout`.
- Tool failures return `tool_error`.
- None of those outcomes approve a requirement.

Tests:

- `tests/test_milestone_group1.py` verifies numeric bound conflict, direct
  opposite predicate, mutually exclusive state, and strict numeric bound
  classification.
- Existing self-consistency tests cover backend status mapping and
  deterministic contradiction paths.
