# Milestone Group 8 Semantic Translation Closure Digest

Milestone group 8 extends the conclusion roadmap after phase 82. The roadmap in
`docs/nl-attestation-conclusion-roadmap.md` closes the first conclusion release
at ADR 0091, but its known remaining gaps still call out weak free-form
translation, structural-only translator agreement, limited semantic
equivalence, and benchmark immaturity for translation quality. Group 8 targets
that gap cluster directly with phases 83 through 88.

## Roadmap Digest

The conclusion roadmap's target path is:

```text
human requirement -> controlled or clarified requirement -> formal claim R
-> R self-check -> R checked against S -> grounded code/trace evidence
-> proof object -> action gate
```

Phases 46-82 made this path operational enough to certify a conclusion release,
but the weakest boundary remained the transition from approved controlled text
to a backend-neutral formal claim. Group 8 makes that boundary explicit,
auditable, and measurable.

Group 8 does not trust raw prose, does not claim general natural-language
correctness, and does not add arbitrary formula equivalence. It introduces a
formal-claim layer, publishes machine-readable DSL v3 semantics, runs a
deterministic two-stage translation pipeline, compares formal claims under
named equivalence profiles, emits repair prompts for failures, and extends the
translation benchmark so false acceptance and ambiguity are first-class release
signals.

## Phase Map

| Phase | Theme | Primary implementation |
|---:|---|---|
| 83 | Formal claim IR | `nlreq.formal_claim`, `formal-claim`, formal claim schemas |
| 84 | Controlled requirement semantics | `nlreq.controlled_semantics`, `controlled-semantics` |
| 85 | Req2LTL-style intermediate translator | `nlreq.semantic_translation`, `semantic-translate` |
| 86 | Semantic agreement gate | `nlreq.semantic_agreement`, `semantic-agreement` |
| 87 | Translation repair and clarification UX | `nlreq.translation_repair`, `translation-repair` |
| 88 | Semantic translation benchmark expansion | `nlreq.translation_benchmark`, `benchmark-translation` |

## Spec And ADR Matrix

| Phase | Spec | ADR | Primary contracts | Verification surface |
|---:|---|---|---|---|
| 83 | `docs/phase-83-formal-claim-ir.md` | `docs/adr/0092-formal-claim-ir-boundary.md` | backend-neutral claim fragments, source spans, required evidence, unsupported-fragment refusal | `tests/test_milestone_group8.py` |
| 84 | `docs/phase-84-controlled-requirement-semantics.md` | `docs/adr/0093-controlled-requirement-semantics.md` | DSL v3 claim-class semantics, construct meanings, evidence requirements, refusal rules | `tests/test_milestone_group8.py` |
| 85 | `docs/phase-85-req2ltl-style-intermediate-translator.md` | `docs/adr/0094-two-stage-semantic-translation-pipeline.md` | controlled text -> semantic IR -> formal claim, stage hashes, refusal codes, clarification questions | `tests/test_milestone_group8.py` |
| 86 | `docs/phase-86-semantic-agreement-gate.md` | `docs/adr/0095-semantic-agreement-equivalence-profiles.md` | candidate comparison, equivalence profiles, blockers, hash-bound review resolution | `tests/test_milestone_group8.py` |
| 87 | `docs/phase-87-translation-repair-clarification-ux.md` | `docs/adr/0096-clarification-repair-protocol.md` | source-span highlights, repair prompts, no-span reasons, review-required decisions | `tests/test_milestone_group8.py` |
| 88 | `docs/phase-88-semantic-translation-benchmark-expansion.md` | `docs/adr/0097-semantic-translation-benchmark-methodology.md` | needs-review outcomes, ambiguity, semantic profile, false acceptance, corpus-scoped scoring | `tests/test_milestone_group8.py` |

## Shared Contracts

- Approved controlled DSL v3 text is the authoritative input for group 8.
- Formal claims are backend-neutral artifacts and do not themselves provide
  proof evidence.
- Unsupported semantic fragments produce refused lowering and no partial formal
  claim.
- Every accepted formal claim fragment carries source spans and a semantic-node
  mapping when the parser can provide them.
- Semantic agreement requires at least two lowered candidates.
- Reviewer resolution selects a candidate by ID and binds the selected candidate
  hash in the agreement report.
- Repair reports never rewrite requirements automatically.
- Benchmark metrics are scoped to corpus cases; extra observed results cannot
  inflate syntactic, semantic, runtime, or false-acceptance numbers.

## Implemented Schemas

- `schemas/formal-claim.schema.json`
- `schemas/formal-claim-lowering-report.schema.json`
- `schemas/controlled-requirement-semantics.schema.json`
- `schemas/semantic-translation-report.schema.json`
- `schemas/semantic-agreement-report.schema.json`
- `schemas/translation-repair-report.schema.json`
- `schemas/requirement-translation-corpus.schema.json`
- `schemas/requirement-translation-results.schema.json`
- `schemas/requirement-translation-benchmark-report.schema.json`

## Verification Surface

`tests/test_milestone_group8.py` covers:

- supported formal-claim lowering for authorization, state, numeric, and event
  claim classes;
- unsupported semantic-node refusal without partial formal claims;
- controlled semantics reference completeness and refusal rules;
- deterministic semantic translation stage hashes;
- parser refusal and repair prompt generation;
- semantic agreement conflict blocking, commutative equivalence, missing
  candidate blockers, and hash-bound review resolution;
- no-op repair behavior after reviewed agreement resolution;
- benchmark ambiguity, needs-review, false-acceptance, missing-case, and
  extra-result scoring.

## Exit Readiness

Group 8 is ready when all phase specs and ADRs are accepted, the schema-backed
APIs expose each semantic translation closure contract, generated schemas are
current, and the focused group-8 tests plus the repository test suite pass.
