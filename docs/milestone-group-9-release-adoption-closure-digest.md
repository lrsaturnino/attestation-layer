# Milestone Group 9 Release And Adoption Closure Digest

Milestone group 9 implements the release and adoption closure implied by
`docs/nl-attestation-conclusion-roadmap.md`: downstream action must be allowed
only after controlled requirement intake, translation, self-checking, system
compatibility, code and trace grounding, evidence retention, and closure
evidence are all represented honestly.

The tracked conclusion roadmap finishes its first release sequence at phase 82.
Group 8 extended the weak semantic translation boundary. Group 9 hardens the
other end of the product path: how the project exposes a real end-to-end gate,
how CI consumes that gate, how public benchmarks prevent false confidence, how
public docs and threat model claims are frozen, and how an extended conclusion
release is certified without overclaiming proof strength.

## Roadmap Digest

The conclusion roadmap's target path is:

```text
human requirement -> approved controlled requirement -> formal claim R
-> R self-check -> R checked against current system spec S
-> code/spec/trace grounding -> proof object -> downstream action gate
```

Group 9 turns that path into release evidence. It does not add a new proof
backend, and it does not claim universal natural-language correctness. It
requires the release machinery to fail closed when any required stage is
missing, unknown, stale, unsigned where signatures are required, or documented
only in Markdown.

## Phase Map

| Phase | Theme | Primary implementation |
|---:|---|---|
| 110 | End-to-end gate hardening | `nlreq.end_to_end_gate`, `requirement-gate-extended` |
| 111 | CI adoption modes | `nlreq.ci_pr_gate`, `ci-adoption` |
| 112 | Extended benchmark corpus | `nlreq.benchmark_reporting`, `benchmark-extended` |
| 113 | Reference brownfield demo | `nlreq.reference_demo`, `reference-demo-extended` |
| 114 | Public SDK and docs freeze | `nlreq.public_sdk`, `public-docs-freeze` |
| 115 | Threat model and TCB review | `nlreq.threat_model`, `tcb-review` |
| 116 | Extended conclusion certification | `nlreq.conclusion_certification`, `extended-conclusion-certify` |

## Spec And ADR Matrix

| Phase | Spec | ADR | Primary contracts | Verification surface |
|---:|---|---|---|---|
| 110 | `docs/phase-110-end-to-end-requirement-gate-hardening.md` | `docs/adr/0119-end-to-end-requirement-gate-contract.md` | required stage list, artifact layout, missing-stage refusal, stable gate hash | `tests/test_milestone_group9.py` |
| 111 | `docs/phase-111-ci-adoption-modes.md` | `docs/adr/0120-ci-adoption-gate-modes.md` | report-only, soft-gate, hard-gate, PR Markdown, machine-result hash | `tests/test_milestone_group9.py` |
| 112 | `docs/phase-112-extended-benchmark-corpus.md` | `docs/adr/0121-extended-benchmark-methodology.md` | required benchmark dimensions, thresholds, missing dimension failure | `tests/test_milestone_group9.py` |
| 113 | `docs/phase-113-reference-brownfield-demo.md` | `docs/adr/0122-reference-brownfield-demo-contract.md` | accepted/refused demo runs, replay bundles, extended gate report checks | `tests/test_milestone_group9.py` |
| 114 | `docs/phase-114-public-sdk-docs-freeze.md` | `docs/adr/0123-public-sdk-documentation-freeze.md` | topic coverage, frozen schemas, compatibility commitments | `tests/test_milestone_group9.py` |
| 115 | `docs/phase-115-threat-model-tcb-review.md` | `docs/adr/0124-threat-model-tcb-review.md` | TCB categories, release artifact hashes, residual risk acceptance | `tests/test_milestone_group9.py` |
| 116 | `docs/phase-116-extended-conclusion-certification.md` | `docs/adr/0125-extended-conclusion-certification.md` | release criteria, producer evidence, schema freeze, signed release bundle | `tests/test_milestone_group9.py` |

## Implemented Schemas

- `schemas/extended-end-to-end-requirement-gate.schema.json`
- `schemas/ci-adoption-policy.schema.json`
- `schemas/extended-ci-pr-gate-report.schema.json`
- `schemas/extended-benchmark-evaluation-report.schema.json`
- `schemas/extended-reference-demo-report.schema.json`
- `schemas/public-documentation-freeze-report.schema.json`
- `schemas/extended-tcb-review-report.schema.json`
- `schemas/extended-conclusion-certification-report.schema.json`

## Shared Contracts

- The extended gate consumes existing end-to-end gate output and adds release
  required stages. It fails closed when required stages are missing.
- CI hard-gate release certification depends on machine-readable JSON output,
  not Markdown text.
- Benchmarks must cover semantic translation, formal system closure, trace
  grounding, adapter evidence, release gates, false closure, false refusal,
  runtime, and counterexample quality.
- Reference demos must include accepted and refused requirements. Refused demo
  cases are valid when the refusal is expected and replayable.
- Public documentation freeze requires topic coverage, schema hashes, and
  compatibility commitments.
- TCB review requires release artifact hashes and explicit acceptance of
  residual risks.
- Extended conclusion certification blocks unless all group 9 release evidence
  is present and passing.

## Exit Readiness

Group 9 is ready when all phase specs and ADRs are accepted, generated schemas
are current, `tests/test_milestone_group9.py` passes, release CLI commands can
produce the new artifacts, and the repository test suite passes.
