# Phase 23 Translator And Drafting MVP

Phase 23 proves the front door from prose draft to controlled DSL v2 to
compositional IR to a first formal lowering artifact.

This phase keeps the trust boundary explicit: drafts are not accepted
requirements, and lowering artifacts are not proof.

## Purpose

The phase lets the Attestation Layer say:

```text
Free-form prose can be preserved with a suggested controlled DSL v2 rewrite,
the rewrite requires explicit approval before parsing, and approved
compositional IR can lower deterministically into a first formal target artifact
or refuse with fragment-level diagnostics.
```

It does not say:

```text
An LLM decides acceptance.
Unapproved drafts are parsed or checked.
The lowered artifact has been model checked.
Temporal claims are proven.
```

## Drafting Trust Model

Drafting artifacts record:

- original prose;
- suggested DSL v2 text;
- diff;
- prompt/model metadata when applicable;
- timestamp;
- approval state.

The parser only accepts approved drafts. `llm_suggested` or unapproved content
is never an approving state.

## Deterministic Lowering

The first translator lowers `RequirementIRV2` into a TLA-oriented skeleton
artifact. It is intentionally narrow and deterministic.

Supported fragments:

- universal scope;
- conjunctions;
- predicates;
- numeric `<=` and `>=`;
- action obligations;
- bounded `within` event obligations;
- state floor/ceiling obligations.

Unsupported nodes refuse with node id, kind, and reason.

## Temporal MVP

Bounded temporal clauses record their bounds in the lowering artifact. A
`within 6 hours` DSL fragment becomes bounded metadata. It does not become
`BOUNDED_CHECKED` until a later backend executes an actual bounded check.

## CLI Shape

Create a draft artifact:

```bash
uv run nlreq draft-controlled original.txt \
  --suggested tests/fixtures/requirements/dsl_v2_redemption.nlreq2 \
  --out /tmp/draft.json
```

Approve a draft:

```bash
uv run nlreq approve-draft /tmp/draft.json \
  --approved-by reviewer@example.invalid \
  --out /tmp/approved-draft.json
```

Lower an approved DSL v2 IR:

```bash
uv run nlreq lower-ir-v2 requirement.ir.v02.json --out /tmp/lowered-tla.json
```

## Implementation Scope

Phase 23 implementation should include:

- draft artifact models and JSON schema;
- explicit draft approval helper;
- refusal when parsing unapproved drafts;
- deterministic IR v2 to TLA-skeleton lowering;
- lowered formal artifact JSON schema;
- fragment-level unsupported diagnostics;
- temporal bound extraction into lowering metadata;
- tests for draft approval, refusal, deterministic lowering, and unsupported
  nodes.

## Evidence Semantics

Drafting and lowering do not satisfy proof evidence.

Lowering can produce a reviewable formal artifact. It cannot produce
`BOUNDED_CHECKED` or `PROVEN_INDUCTIVE`. Unsupported or unapproved artifacts are
non-approving.

## Success Criterion

Phase 23 succeeds when:

- free-form prose can be stored with a suggested DSL v2 draft and provenance;
- unapproved drafts cannot be parsed into IR;
- approved drafts parse into `RequirementIRV2`;
- `RequirementIRV2` lowers deterministically into one formal target artifact;
- unsupported nodes refuse with fragment-level diagnostics;
- temporal bounds are recorded without inflating evidence;
- and LLM-originated content is provenance-marked and never auto-accepted.

## Boundary

This phase is not network LLM integration, full NL translation, complete TLA
lowering, model checking, `S ∧ R`, source analysis, proof aggregation, or
closure gating.
