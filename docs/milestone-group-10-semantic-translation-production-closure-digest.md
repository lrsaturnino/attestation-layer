# Milestone Group 10 Semantic Translation Production Closure Digest

Milestone group 10 is the first implementation group in
`docs/conclusion-real-evidence-closure-roadmap.md`. It covers phases 117 through
123 and converts the existing semantic-translation skeleton into a stricter
front-door evidence path.

## Roadmap Digest

The real-evidence roadmap says the project is close in shape but not yet close
in proof strength. The weakest current boundary is still the front of the
pipeline:

```text
human requirement -> approved controlled requirement -> semantic decomposition
-> formal claim R -> self-consistency and downstream evidence gates
```

Milestone group 10 makes that boundary fail closed. Raw free-form text must be
retained and rewritten into controlled text through a hash-bound approval path.
Approved text can then be parsed into an explicit semantic decomposition tree,
lowered deterministically into formal claim IR, compared across independent
translator candidates, repaired only through versioned controlled-form updates,
checked against a documented contradiction taxonomy, and scored against a
release benchmark where false semantic acceptance blocks release.

## Phase Map

| Phase | Theme | Primary implementation |
|---:|---|---|
| 117 | Production free-form intake runtime | `nlreq.intake` runtime records, state transitions, selected approved text |
| 118 | Rewrite provenance and replay | `nlreq.intake` prompt registry and rewrite replay bundles |
| 119 | Semantic decomposition translator | `nlreq.semantic_translation` decomposition tree and approved-text enforcement |
| 120 | Translator ensemble calibration | `nlreq.semantic_agreement` calibration report and false-acceptance blockers |
| 121 | Clarification and repair UX hardening | `nlreq.translation_repair` controlled-form version history |
| 122 | ALICE-grade self-consistency | `nlreq.requirement_self_consistency` taxonomy and untrusted suggestions |
| 123 | Semantic translation benchmark release bar | `nlreq.translation_benchmark` release thresholds and release-bar report |

## Spec And ADR Matrix

| Phase | Spec | ADR | Primary contracts | Verification surface |
|---:|---|---|---|---|
| 117 | `docs/phase-117-production-free-form-intake-runtime.md` | `docs/adr/0126-production-free-form-intake-runtime.md` | drafted/proposed/approved/rejected/superseded state, selected controlled hash, rejected selection blocking | `tests/test_milestone_group10.py` |
| 118 | `docs/phase-118-rewrite-provenance-and-replay.md` | `docs/adr/0127-rewrite-provenance-and-replay.md` | prompt registry, retained outputs, proposal/approval replay hashes | `tests/test_milestone_group10.py` |
| 119 | `docs/phase-119-semantic-decomposition-translator.md` | `docs/adr/0128-semantic-decomposition-translator.md` | approved text hash enforcement, decomposition tree, deterministic lowering boundary | `tests/test_milestone_group10.py` |
| 120 | `docs/phase-120-translator-ensemble-calibration.md` | `docs/adr/0129-translator-ensemble-calibration.md` | calibrated agreement observations, false acceptance/refusal budgets | `tests/test_milestone_group10.py` |
| 121 | `docs/phase-121-clarification-and-repair-ux-hardening.md` | `docs/adr/0130-clarification-repair-ux.md` | source-span prompts, response records, proposed versions, explicit approval selection | `tests/test_milestone_group10.py` |
| 122 | `docs/phase-122-alice-grade-self-consistency.md` | `docs/adr/0131-requirement-contradiction-taxonomy.md` | contradiction taxonomy, deterministic blockers, untrusted LLM suggestions | `tests/test_milestone_group10.py` |
| 123 | `docs/phase-123-semantic-translation-benchmark-release-bar.md` | `docs/adr/0132-semantic-translation-benchmark-release-bar.md` | corpus-scoped metrics, false acceptance count, release thresholds | `tests/test_milestone_group10.py` |

## Shared Contracts

- Free-form input is retained as evidence, not parsed as a formal requirement.
- Controlled text reaches formal parsing only when the configured path has an
  approved exact text hash.
- Rewrite replay bundles retain non-deterministic outputs; replay explains the
  rewrite even when an LLM cannot reproduce identical text.
- Semantic decomposition is an explicit intermediate artifact and the formal
  claim lowerer consumes deterministic semantic IR, not opaque prose.
- High-assurance semantic agreement fails closed on unreviewed disagreement and
  calibration false acceptance.
- Repair responses create new proposed controlled-form versions. They do not
  silently replace the selected approved version.
- LLM contradiction suggestions are advisory and cannot pass or fail a
  requirement.
- Benchmark release bars are corpus-scoped; extra observed results cannot
  improve required-case coverage.

## Implemented Schemas

- `schemas/free-form-intake-runtime-record.schema.json`
- `schemas/rewrite-prompt-registry.schema.json`
- `schemas/rewrite-replay-bundle.schema.json`
- `schemas/semantic-decomposition-tree.schema.json`
- `schemas/semantic-agreement-calibration-report.schema.json`
- `schemas/translation-repair-report.schema.json`
- `schemas/requirement-contradiction-taxonomy.schema.json`
- `schemas/requirement-translation-release-thresholds.schema.json`
- `schemas/requirement-translation-release-bar-report.schema.json`

## Exit Readiness

Group 10 exits when the specs and ADRs are accepted, generated schemas are
current, `tests/test_milestone_group10.py` passes, and the full repository test
suite confirms the new stricter contracts remain backward compatible with the
existing group-8 and group-9 pipeline artifacts.
