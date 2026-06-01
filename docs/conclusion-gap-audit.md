# Conclusion Gap Audit

This audit maps conclusion roadmap milestone group 1 to implemented artifacts.

| Phase | Capability | Status | Primary Artifacts |
|---:|---|---|---|
| 46 | Conclusion definition and gap checklist | Implemented | `docs/conclusion-definition.md`, `docs/conclusion-gap-checklist.json`, `src/nlreq/conclusion.py` |
| 47 | Free-form intake and controlled rewrite | Implemented | `src/nlreq/intake.py`, `schemas/free-form-intake.schema.json`, `schemas/controlled-rewrite-proposal.schema.json` |
| 48 | Controlled DSL v3 | Implemented | `src/nlreq/dsl_v3.py`, `src/nlreq/dsl_v3.lark`, `nlreq ir-v3` |
| 49 | Hash-bound review workflow | Implemented | `src/nlreq/review_workflow.py`, `schemas/approval-workflow.schema.json` |
| 50 | Product refusal surface v2 | Implemented | `src/nlreq/refusal.py`, `schemas/product-refusal-report.schema.json` |
| 51 | Multi-pass translator workbench | Implemented | `src/nlreq/translator_workbench.py`, `schemas/translator-run.schema.json` |
| 52 | Bidirectional provenance and clarification | Implemented | `src/nlreq/provenance.py`, `schemas/provenance-graph.schema.json` |
| 53 | Logical translator agreement | Implemented | `src/nlreq/logical_agreement.py`, `schemas/logical-translation-agreement-report.schema.json` |
| 54 | Contradiction taxonomy v2 | Implemented | `src/nlreq/requirement_self_consistency.py`, `docs/contradiction-taxonomy-v2.md` |
| 55 | Requirement translation corpus | Implemented | `benchmarks/requirements-translation/corpus.json`, `src/nlreq/translation_benchmark.py` |

## Remaining Groups

Milestone groups 2-4 remain planned by the conclusion roadmap. Group 1 does not
claim production Apalache/TLC integration, production source extraction,
additional language adapters, signed evidence, or conclusion certification.

## CI Check

The gap checklist enforces phase references, ADR numbering, and one group-1
owner item per phase:

```bash
uv run nlreq conclusion-gap-check docs/conclusion-gap-checklist.json
```
