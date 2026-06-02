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

## Implementation Specification

### Inputs

The gate consumes two or more `FormalClaimLoweringReport` artifacts. Each input
is wrapped as a `FormalClaimAgreementCandidate` with candidate ID and translator
ID. Candidates may come from the deterministic DSL v3 parser, the translator
workbench, or an audited second-model pass, but every candidate must already
lower to formal claim IR.

### Outputs

The output is `SemanticAgreementReport`, which records:

- requirement ID;
- candidate hashes;
- pairwise comparisons against the baseline candidate;
- blockers for missing, mismatched, or unlowered candidates;
- optional reviewer resolution;
- `acceptance_allowed` decision.

The report is the authoritative artifact. Markdown or product UX should render
from this JSON rather than recomputing comparisons.

### Equivalence Profile Semantics

`canonical_formal_claim_equality` compares typed formal-claim signatures.

`alpha_identifier_equivalence` permits stable renaming of identifiers while
preserving roles, operators, predicates, temporal bounds, and metadata.

`commutative_claim_equivalence` permits reordering of premises and obligations
that are modeled as conjunctions.

`unsupported` means no supported profile established equivalence. It is not a
weaker agreement mode.

### Review Resolution

Reviewer resolution is allowed only after a disagreement. The reviewer selects
one candidate by ID. The report binds that selection to the selected candidate
hash; if a supplied hash does not match, the disagreement remains blocking.

Review resolution does not prove equivalence. It records an auditable human
choice of the candidate that best preserves requirement intent.

### Decision Rules

`status == "agreed"` when all comparisons agree under supported profiles and
there are no blockers.

`status == "disagreed"` when any comparison conflicts and no valid review
resolution is present.

`status == "needs_review"` when the candidate set itself is incomplete or
invalid.

`status == "resolved_by_review"` when a valid hash-bound reviewer resolution
selects one candidate after disagreement.

## Exit Criteria

This phase exits when:

- equivalent candidates can agree through supported profiles;
- conflicting candidates block acceptance;
- reviewer resolution can unblock a known disagreement;
- source spans are preserved for conflicts when available.

## Tests

`tests/test_milestone_group8.py` verifies commutative equivalence, conflict
blocking, and reviewer resolution.

## Out Of Scope

This phase does not prove arbitrary formula equivalence. Unsupported
equivalence remains blocked or review-bound.
