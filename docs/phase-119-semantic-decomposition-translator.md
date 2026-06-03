# Phase 119 Semantic Decomposition Translator

Phase 119 upgrades semantic translation into an explicit decomposition pipeline.

## Purpose

The translator must not lower opaque prose directly into a formal claim. It must
first produce an inspectable semantic decomposition tree with source spans and
then lower deterministic semantic IR into formal claim IR.

## Contracts

`src/nlreq/semantic_translation.py` defines:

- `SemanticDecompositionNode`
- `SemanticDecompositionTree`
- `build_semantic_decomposition_tree`
- `translate_controlled_requirement_to_formal_claim`

`SemanticTranslationReport` now records:

- `semantic_decomposition`;
- `semantic_decomposition_hash`;
- approved controlled text hash when provided;
- refusal code `NLR-UNAPPROVED-CONTROLLED-TEXT` when approval is required and
  the exact hash is missing or mismatched.

## Pipeline

```text
approved controlled text -> DSL v3 semantic IR -> decomposition tree
-> deterministic formal claim lowering
```

The decomposition tree records each node's role:

- `root`
- `scope`
- `premise`
- `action`
- `obligation`
- `child`

## Approval Boundary

Callers can set `require_approved_controlled_text=True`. In that mode the
translator refuses before parsing unless `approved_controlled_text_hash` equals
the controlled text hash.

## Lowering Boundary

Formal claim lowering consumes `RequirementIRV2`, not raw text. The
decomposition tree is an auditable intermediate artifact, while the formal claim
lowerer remains deterministic and refuses unsupported fragments.

## Exit Criteria

This phase exits when:

- unapproved controlled text can be refused before parsing;
- accepted translations include a decomposition tree and hash;
- source-span-bearing nodes survive decomposition;
- formal claim hashes remain deterministic;
- tests cover accepted and refused translation paths.
