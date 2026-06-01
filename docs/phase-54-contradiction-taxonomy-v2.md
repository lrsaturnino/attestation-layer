# Phase 54 Contradiction Taxonomy v2

Phase 54 makes self-consistency a first-class requirement analysis backend.

## Taxonomy

The v2 taxonomy is documented in `docs/contradiction-taxonomy-v2.md` and
implemented in `src/nlreq/requirement_self_consistency.py`.

## Deterministic Checks

The checker handles direct opposite predicates, impossible literal
comparisons, numeric bound conflicts, duplicate obligation conflicts, temporal
impossibility, state conflicts, and overlapping opposite obligations where the
IR exposes enough structure.

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
