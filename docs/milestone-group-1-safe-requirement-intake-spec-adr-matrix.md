# Milestone Group 1 Safe Requirement Intake Spec And ADR Matrix

Milestone group 1 is roadmap Step 1, covering phases 46 through 55. This matrix
binds each phase to its implementation spec, ADR, primary artifact contracts,
and current verification surface.

## Coverage Matrix

| Phase | Spec | ADR | Primary Contracts | Verification Surface |
|---:|---|---|---|---|
| 46 | `docs/phase-46-conclusion-definition-gap-audit.md` | `docs/adr/0055-conclusion-definition-release-bars-evidence-labels.md` | conclusion definition, gap checklist, release bars | `conclusion-gap-checklist`, `tests/test_milestone_group1.py` |
| 47 | `docs/phase-47-free-form-intake-controlled-rewrite.md` | `docs/adr/0056-free-form-intake-controlled-rewrite-approval.md` | free-form intake, rewrite proposal, approval hash binding | `intake-draft`, `intake-approve`, `intake-diff` |
| 48 | `docs/phase-48-controlled-requirement-dsl-v3.md` | `docs/adr/0057-controlled-requirement-dsl-v3.md` | DSL v3 grammar, canonical formatter, IR v0.2 mapping | `ir-v3`, DSL v3 fixture tests |
| 49 | `docs/phase-49-requirement-review-approval-workflow.md` | `docs/adr/0058-requirement-review-approval-hash-binding.md` | approval workflow, checklist, stale review report | `review-open`, `review-approve`, `review-status` |
| 50 | `docs/phase-50-product-refusal-surface.md` | `docs/adr/0059-product-refusal-taxonomy.md` | refusal findings, stable `NLR-*` codes, Markdown renderer | `refusal-render`, `requirement-gate --markdown-out` |
| 51 | `docs/phase-51-multi-pass-nl-translator-workbench.md` | `docs/adr/0060-multi-pass-translator-workbench.md` | translator run, candidate, selection artifacts | `translate-candidates`, `translate-compare`, `translate-select` |
| 52 | `docs/phase-52-bidirectional-provenance-clarification.md` | `docs/adr/0061-bidirectional-provenance-clarification.md` | provenance graph, clarification request/response, clarified text | `provenance-graph`, `clarify`, `apply-clarification` |
| 53 | `docs/phase-53-logical-translator-agreement.md` | `docs/adr/0062-logical-translator-agreement.md` | logical agreement report, equivalence hierarchy | `logical-translator-agreement` |
| 54 | `docs/phase-54-contradiction-taxonomy.md` | `docs/adr/0063-requirement-contradiction-taxonomy.md` | self-consistency report, contradiction codes | `requirement-self-consistency` |
| 55 | `docs/phase-55-requirement-corpus-for-translation.md` | `docs/adr/0064-requirement-translation-corpus.md` | translation corpus, observed results, benchmark report | `benchmark-translation` |

## Group-Level Invariants

- Raw free-form text is never parsed until an approved controlled rewrite is
  hash-bound to the original text, proposed controlled text, and diff.
- Controlled DSL v3 is canonicalized before parsing so source spans are stable
  over the approved controlled text.
- Human review approvals bind artifact hashes and become stale when reviewed
  artifacts change.
- Refusals preserve source spans where available and otherwise explain why a
  span is unavailable.
- Translator candidates are untrusted until agreement or explicit review
  selection resolves them.
- Clarification produces a new controlled text artifact; it never mutates the
  previous approved text in place.
- Logical agreement can prove supported equivalence, but unsupported
  equivalence stays `needs_review`.
- Self-consistency contradictions use stable codes and run before backend
  execution when deterministic taxonomy classes apply.
- Translation quality is benchmarked separately from formal backend outcomes.

## Current Implementation Boundary

Group 1 implements a production-shaped artifact and CLI surface for safe
requirement intake. It still treats LLM translation as an untrusted future
candidate producer; no external LLM API is required or trusted by the current
implementation. Formal backend maturity, real `S and R` composition, brownfield
grounding, adapter productionization, evidence signing, and release
certification are owned by later milestone groups.
