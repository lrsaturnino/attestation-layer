# ADR 0128: Semantic Decomposition Translator

## Status

Accepted

## Context

The existing semantic translator parsed DSL v3 into semantic IR and lowered it
into formal claim IR. The real-evidence roadmap requires an explicit
Req2LTL-style decomposition boundary and an approval check that can stop
unapproved controlled text before parsing.

## Decision

Add `SemanticDecompositionTree` as the auditable intermediate artifact and add
optional approved-controlled-text hash enforcement to
`translate_controlled_requirement_to_formal_claim`.

## Invariants

- Formal claim lowering consumes deterministic semantic IR, not opaque prose.
- The decomposition tree records node role, kind, label, source spans, and
  child structure.
- If approved text is required, missing or mismatched hashes refuse before
  parsing.
- Decomposition and formal claim artifacts are hash-linked in the translation
  report.

## Consequences

The translator now exposes a reviewable semantic tree and a stricter product
entry point for approved controlled text.

## Rejected Alternatives

Treating `RequirementIRV2` alone as the user-facing decomposition was rejected
because it is optimized for lowering, not review.

Allowing unapproved controlled text in high-assurance mode was rejected because
it bypasses the intake evidence chain.

## Validation

`tests/test_milestone_group10.py` verifies unapproved hash refusal and accepted
translation with decomposition hashes.
