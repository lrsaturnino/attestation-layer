# Phase 34 Translator Agreement Gate

Phase 34 treats NL-to-formal translation as untrusted. Multiple candidate
translations must structurally agree before downstream self-consistency,
`S and R`, trace grounding, or proof closure can rely on the formalized
requirement.

## Purpose

The phase lets the Attestation Layer say:

```text
These translation candidates agree structurally, or they disagree at this
fragment and require clarification before verification continues.
```

It does not say:

```text
The natural-language requirement was perfectly interpreted.
LLM-originated translations can auto-approve themselves.
Structural equality proves full semantic equivalence.
```

## Implementation Scope

Phase 34 implementation includes:

- translation candidate and agreement report models;
- structural signatures for compositional IR that ignore provenance noise;
- disagreement detection across actions, predicates, bounds, obligations, and
  tree shape;
- clarification questions for material disagreements;
- explicit blocker for unapproved LLM-originated candidates;
- CLI command for `translator-agreement`;
- JSON schemas and tests.

## Evidence Semantics

Agreement is a gate, not proof. An agreed report allows downstream deterministic
and solver-backed checks to consume the candidate formalization. A disagreed or
needs-review report cannot close proof.

LLM candidates require explicit approval even when they structurally match a
deterministic candidate. The approval acknowledges review of the translation; it
does not make the LLM a proof producer.

## Success Criterion

Phase 34 succeeds when:

- structurally equal candidates produce an agreed report;
- material differences produce deterministic disagreement artifacts;
- disagreement reports include a fragment path and clarification question;
- unapproved LLM candidates block auto-approval;
- the report is schema-backed and CLI-addressable.

## Boundary

This phase does not solve natural-language intent recovery. It provides a
deterministic refusal surface when translation strategies disagree or when a
candidate comes from an unreviewed LLM source.
