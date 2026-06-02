# Conclusion Gap Audit

This audit maps conclusion roadmap phases 46 through 82 to implemented
artifacts.

| Phase | Capability | Status | Primary Artifacts |
|---:|---|---|---|
| 46 | Conclusion definition and gap checklist | Implemented | `docs/conclusion-definition.md`, `docs/conclusion-gap-checklist.json`, `src/nlreq/conclusion.py` |
| 47 | Free-form intake and controlled rewrite | Implemented | `src/nlreq/intake.py`, `schemas/free-form-intake.schema.json`, `schemas/controlled-rewrite-proposal.schema.json` |
| 48 | Controlled DSL v3 | Implemented | `src/nlreq/dsl_v3.py`, `src/nlreq/dsl_v3.lark`, `nlreq ir-v3` |
| 49 | Hash-bound review workflow | Implemented | `src/nlreq/review_workflow.py`, `schemas/approval-workflow.schema.json`, `schemas/review-checklist-v2.schema.json` |
| 50 | Product refusal surface v2 | Implemented | `src/nlreq/refusal.py`, `schemas/product-refusal-report.schema.json` |
| 51 | Multi-pass translator workbench | Implemented | `src/nlreq/translator_workbench.py`, `schemas/translator-run.schema.json` |
| 52 | Bidirectional provenance and clarification | Implemented | `src/nlreq/provenance.py`, `schemas/provenance-graph.schema.json` |
| 53 | Logical translator agreement | Implemented | `src/nlreq/logical_agreement.py`, `schemas/logical-translation-agreement-report.schema.json` |
| 54 | Contradiction taxonomy v2 | Implemented | `src/nlreq/requirement_self_consistency.py`, `docs/contradiction-taxonomy-v2.md` |
| 55 | Requirement translation corpus | Implemented | `benchmarks/requirements-translation/corpus.json`, `src/nlreq/translation_benchmark.py` |
| 56 | Apalache backend | Implemented | `src/nlreq/formal_backend.py`, `docs/phase-56-apalache-backend-production-integration.md` |
| 57 | TLC backend | Implemented | `src/nlreq/formal_backend.py`, `docs/phase-57-tlc-backend-production-integration.md` |
| 58 | TLA projection v2 | Implemented | `src/nlreq/tla_projection_v2.py`, `schemas/tla-projection-v2-report.schema.json` |
| 59 | Counterexample normalization v2 | Implemented | `src/nlreq/counterexample_v2.py`, `schemas/counterexample-normalization-v2-report.schema.json` |
| 60 | `S and R` composition | Implemented | `src/nlreq/system_composition.py`, `schemas/s-and-r-composition-report.schema.json` |
| 61 | Evidence boundary | Implemented | `src/nlreq/evidence_boundary.py`, `schemas/proof-evidence-boundary-report.schema.json` |
| 62 | Spec extraction runner | Implemented | `src/nlreq/spec_extraction.py`, `docs/phase-62-specula-style-extraction-runner.md` |
| 63 | Code-to-spec manifest v2 | Implemented | `src/nlreq/spec_drift.py`, `schemas/code-spec-manifest.schema.json` |
| 64 | Spec freshness lockfile | Implemented | `src/nlreq/spec_freshness.py`, `schemas/spec-freshness-lockfile.schema.json` |
| 65 | Runtime trace SDK | Implemented | `src/nlreq/runtime_trace_sdk.py`, `schemas/trace-producer-registry.schema.json` |
| 66 | Trace normalization v2 | Implemented | `src/nlreq/trace_normalization_v2.py`, `schemas/trace-normalization-v2-report.schema.json` |
| 67 | Solidity adapter | Implemented | `src/nlreq/production_source_adapters.py`, `nlreq adapter-certify-v2 --language solidity` |
| 68 | Go adapter | Implemented | `src/nlreq/production_source_adapters.py`, `nlreq adapter-certify-v2 --language go` |
| 69 | TypeScript adapter | Implemented | `src/nlreq/production_source_adapters.py`, `nlreq adapter-certify-v2 --language typescript` |
| 70 | Rust or Java adapter | Implemented | `src/nlreq/production_source_adapters.py`, `nlreq adapter-certify-v2 --language rust` |
| 71 | Adapter certification v2 | Implemented | `src/nlreq/adapter_certification.py`, `schemas/adapter-certification-report.schema.json` |
| 72 | Cross-language proof object | Implemented | `src/nlreq/cross_language.py`, `schemas/cross-language-proof-object.schema.json` |
| 73 | Evidence artifact store | Implemented | `src/nlreq/artifact_store.py`, `schemas/artifact-store-manifest.schema.json` |
| 74 | Signed evidence | Implemented | `src/nlreq/signed_evidence.py`, `schemas/signed-evidence-envelope.schema.json` |
| 75 | CI and PR gate | Implemented | `src/nlreq/ci_pr_gate.py`, `schemas/ci-pr-gate-report.schema.json` |
| 76 | Benchmark v2 | Implemented | `src/nlreq/benchmark_v2.py`, `schemas/benchmark-v2-report.schema.json` |
| 77 | Verification cache | Implemented | `src/nlreq/verification_cache.py`, `schemas/verification-cache-index.schema.json` |
| 78 | Waiver governance v2 | Implemented | `src/nlreq/policy_v2.py`, `schemas/waiver-audit-report.schema.json` |
| 79 | Threat model and TCB | Implemented | `src/nlreq/threat_model.py`, `schemas/threat-model-report.schema.json` |
| 80 | Reference brownfield demo | Implemented | `src/nlreq/reference_demo.py`, `schemas/reference-demo-manifest.schema.json` |
| 81 | Public docs and SDK | Implemented | `src/nlreq/public_sdk.py`, `schemas/public-documentation-index.schema.json` |
| 82 | Conclusion certification | Implemented | `src/nlreq/conclusion_certification.py`, `schemas/conclusion-certification-report.schema.json` |

## CI Check

The gap checklist enforces phase references, ADR numbering, and one owner item
per conclusion phase:

```bash
uv run nlreq conclusion-gap-check docs/conclusion-gap-checklist.json
```
