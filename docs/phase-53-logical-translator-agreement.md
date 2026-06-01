# Phase 53 Logical Translator Agreement

Phase 53 moves translator comparison beyond structural equality for supported
fragments.

## Methods

The method hierarchy is:

1. Normalized IR equality.
2. Alpha-renaming equivalence.
3. Commutative predicate equivalence.
4. SMT simple predicate equivalence.
5. Bounded trace equivalence when witnesses exist.

Unsupported equivalence remains `needs_review` or `conflict`, never `agreed`.

## Contracts

`src/nlreq/logical_agreement.py` defines
`LogicalTranslationAgreementReport`.

CLI:

```bash
uv run nlreq logical-translator-agreement translation-agreement-input.json \
  --out logical-agreement.json
```

## Invariants

- Equivalent simple translations do not require manual clarification.
- Semantic conflicts still block.
- The report records the method used and method limitations.

## Exit Criteria

Tests cover equivalent-but-different translations and conflict handling.

## Implementation Spec

Input artifacts:

- Two or more `TranslationCandidate` records with `RequirementIRV2` payloads.

Output artifacts:

- `LogicalTranslationAgreementReport` with candidate hashes, pairwise
  comparisons, final status, and limitations.

Equivalence hierarchy:

- `normalized_ir_equality` compares full canonical semantic signatures.
- `alpha_renaming` permits renamed scopes and bound identifiers.
- `commutative_predicate_equivalence` permits reordered `and` children and
  equality operands.
- `smt_simple_predicate_equivalence` is reserved for simple predicate fragments
  and currently uses the deterministic simple-fragment signature.
- `bounded_trace_equivalence` requires trace witnesses and returns
  `needs_review` until supplied.

Decision behavior:

- Any conflict makes the report `conflict`.
- Any unsupported temporal witness need makes the report `needs_review`.
- Only supported equivalence methods can produce `agreed`.

Tests:

- `tests/test_milestone_group1.py` verifies equivalent translations that differ
  by scope naming and predicate ordering.

Out of scope:

- This phase does not claim general theorem-proving equivalence across all IR
  fragments. Unsupported equivalence remains review-bound.
