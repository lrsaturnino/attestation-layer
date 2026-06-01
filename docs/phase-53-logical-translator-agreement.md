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
