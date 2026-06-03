# Milestone Group 12 Brownfield Grounding Closure Digest

Milestone group 12 implements phases 131 through 137 from
`docs/conclusion-real-evidence-closure-roadmap.md`. It turns brownfield
grounding from mostly scaffolded reports into production evidence gates over
current code, reviewed specs, freshness locks, candidate extraction, runtime
trace producers, and trace validation closure.

## Roadmap Digest

Groups 10 and 11 made controlled requirements and formal backend checks harder
to overclaim. Group 12 closes the next gap:

```text
formal claim R -> affected source modules -> reviewed coverage for S
-> freshness lock over code and spec hashes -> candidate extraction only for gaps
-> human promotion of generated specs -> real runtime traces
-> trace validation gate with explicit blocker outcomes
```

The main release risk is checking a requirement against an idealized or stale
model. This group blocks that risk by separating adapter-deterministic impact
from semantic hints, distinguishing reviewed coverage from candidate coverage,
failing stale specs in CI, keeping generated specs untrusted until review, and
labeling trace evidence as grounding rather than proof.

## Phase Map

| Phase | Theme | Primary implementation |
|---:|---|---|
| 131 | Production source impact | `nlreq.source_impact.ProductionSourceImpactReport` |
| 132 | Coverage manifest v2 | `nlreq.coverage_alignment.CodeSpecCoverageManifestV2` |
| 133 | Freshness and drift CI | `nlreq.spec_freshness.SpecFreshnessDriftCiReport` |
| 134 | Specula-style extraction | `nlreq.spec_extraction.SpeculaExtractionIntegrationReport` |
| 135 | Candidate review and promotion | `nlreq.spec_extraction.CandidateSpecReviewReport` |
| 136 | Runtime trace producer SDK | `nlreq.runtime_trace_sdk.TraceProducerEvidenceReport` |
| 137 | Trace validation gate | `nlreq.trace_validation.TraceValidationGateReport` |

## Spec And ADR Matrix

| Phase | Spec | ADR | Primary contracts | Verification surface |
|---:|---|---|---|---|
| 131 | `docs/phase-131-production-source-impact.md` | `docs/adr/0140-production-source-impact-semantics.md` | symbol resolution, call graph impact, trace touchpoints, non-gateable semantic hints | `tests/test_milestone_group12.py` |
| 132 | `docs/phase-132-code-to-spec-coverage-manifest-v2.md` | `docs/adr/0141-code-to-spec-coverage-manifest-v2.md` | reviewed coverage, candidate blocking, dependency propagation, coverage thresholds | `tests/test_milestone_group12.py` |
| 133 | `docs/phase-133-spec-freshness-and-drift-ci.md` | `docs/adr/0142-spec-freshness-drift-ci.md` | timestamped locks, source/spec hash drift, validation age, stale-spec refusal | `tests/test_milestone_group12.py` |
| 134 | `docs/phase-134-specula-style-extraction-integration.md` | `docs/adr/0143-specula-style-extraction-trust-model.md` | candidate-only generated specs, structural validation, trace validation requirement | `tests/test_milestone_group12.py` |
| 135 | `docs/phase-135-candidate-spec-review-and-promotion.md` | `docs/adr/0144-candidate-spec-review-promotion.md` | reviewer identity, candidate hash binding, promotion/rejection reports | `tests/test_milestone_group12.py` |
| 136 | `docs/phase-136-runtime-trace-producer-sdk-production.md` | `docs/adr/0145-runtime-trace-producer-sdk.md` | producer identity, runtime metadata, loss records, replay input retention, signing policy | `tests/test_milestone_group12.py` |
| 137 | `docs/phase-137-trace-validation-gate-production.md` | `docs/adr/0146-trace-validation-closure-policy.md` | satisfied, violation, coverage gap, lossy, stale, unsupported outcomes | `tests/test_milestone_group12.py` |

## Implemented Schemas

- `schemas/production-source-impact-report.schema.json`
- `schemas/code-spec-coverage-manifest-v2.schema.json`
- `schemas/code-spec-coverage-gate-report-v2.schema.json`
- `schemas/spec-freshness-lockfile-v2.schema.json`
- `schemas/spec-freshness-drift-ci-report.schema.json`
- `schemas/specula-extraction-integration-report.schema.json`
- `schemas/candidate-spec-review-report.schema.json`
- `schemas/trace-producer-evidence-report.schema.json`
- `schemas/trace-validation-gate-report.schema.json`

## Shared Contracts

- Missing or ambiguous source symbols block closure before coverage checks.
- Semantic impact suggestions are recorded as review hints and cannot create
  gateable affected modules by themselves.
- Reviewed and fresh formal specs are the only coverage entries that allow
  closure.
- Candidate, draft, rejected, missing, stale, partial, unsupported, and
  dependency-gapped coverage blocks closure.
- Freshness CI compares source and spec hashes and can also block validation
  records that are too old for policy.
- Generated candidate specs remain draft artifacts until a reviewer promotes
  the exact candidate hash.
- Runtime trace producers must identify producer, runtime, replay input hashes,
  loss records, and signing key metadata where policy requires signatures.
- Trace validation is grounding evidence. It never upgrades trace satisfaction
  into formal proof.

## Exit Readiness

Group 12 exits when specs and ADRs are accepted, schemas are generated, CLI
commands can emit the new reports, `tests/test_milestone_group12.py` passes, and
the broader suite confirms existing group 10 and 11 paths remain compatible with
brownfield grounding gates.
