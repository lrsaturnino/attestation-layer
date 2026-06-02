# Phase 86 Semantic Agreement Gate

Phase 86 compares translator candidates at the formal-claim layer.

## Purpose

Structural translator agreement can miss or over-report semantic differences.
This phase adds a gate over formal claim candidates with explicit equivalence
profiles and review resolution.

## Contracts

`src/nlreq/semantic_agreement.py` defines:

- `FormalClaimAgreementCandidate`
- `SemanticAgreementReport`
- `SemanticAgreementComparison`
- `SemanticAgreementResolution`

Schema:

- `schemas/semantic-agreement-report.schema.json`

CLI:

```bash
uv run nlreq semantic-agreement claim-a.json claim-b.json --out semantic-agreement.json
```

Reviewer resolution:

```bash
uv run nlreq semantic-agreement claim-a.json claim-b.json \
  --resolution-candidate-id candidate-1 \
  --resolution-reason "reviewer selected canonical claim" \
  --approved-by reviewer@example.invalid \
  --approved-at 2026-06-02T00:00:00Z \
  --out semantic-agreement.json
```

## Equivalence Profiles

Profiles are tried in order:

1. `canonical_formal_claim_equality`
2. `alpha_identifier_equivalence`
3. `commutative_claim_equivalence`
4. `unsupported`

Any unsupported or conflicting comparison blocks acceptance unless a reviewer
provides a hash-bound resolution selecting one candidate.

## Decision Semantics

Report status values:

- `agreed`: all candidates agree under supported profiles;
- `disagreed`: at least one comparison conflicts;
- `needs_review`: required candidates or formal claims are missing;
- `resolved_by_review`: a reviewer approved a selected candidate after
  disagreement.

`acceptance_allowed` is true only for `agreed` or `resolved_by_review`.

## Failure Behavior

The gate blocks when:

- fewer than two candidates are supplied;
- candidate requirement IDs differ;
- any candidate did not lower to formal claim IR;
- no supported profile proves equivalence.

## Exit Criteria

This phase exits when:

- equivalent candidates can agree through supported profiles;
- conflicting candidates block acceptance;
- reviewer resolution can unblock a known disagreement;
- source spans are preserved for conflicts when available.

## Tests

`tests/test_milestone_group5.py` verifies commutative equivalence, conflict
blocking, and reviewer resolution.

## Out Of Scope

This phase does not prove arbitrary formula equivalence. Unsupported
equivalence remains blocked or review-bound.

