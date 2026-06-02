# Milestone Group 7 Release Hardening, Public Docs, And Certification Digest

Milestone group 7 is group G from
`docs/nl-attestation-conclusion-roadmap.md`, covering phases 79 through 82.
It starts after evidence retention, producer signing, CI gating, benchmark
evaluation, cache semantics, and waiver governance are available.

## Roadmap Digest

Group 7 turns the conclusion roadmap into a release decision. The project must
publish the trusted computing base, prove that a brownfield demo is reproducible,
give adopters a real public documentation and SDK path, and certify the release
from machine-readable evidence instead of maintainer assertion.

The group does not add new proof power. It hardens the public claim boundary:
what is trusted, what is demonstrated, what is documented, and what is certified.

## Phase Map

| Phase | Theme | Primary implementation |
|---:|---|---|
| 79 | Threat model and TCB audit | `nlreq.threat_model`, `threat-model`, threat-model report schema |
| 80 | Reference brownfield demo | `nlreq.reference_demo`, `reference-demo-check`, manifest and report schemas |
| 81 | Public documentation and SDK | `nlreq.public_sdk`, `public-docs-index`, `public-docs-check` |
| 82 | Conclusion release certification | `nlreq.conclusion_certification`, `conclusion-certify` |

## Spec And ADR Matrix

| Phase | Spec | ADR | Primary contracts | Verification surface |
|---:|---|---|---|---|
| 79 | `docs/phase-79-threat-model-tcb-audit.md` | `docs/adr/0088-threat-model-tcb.md` | TCB components, threat scenarios, release claim boundaries | `tests/test_milestone_group7.py` |
| 80 | `docs/phase-80-reference-brownfield-demo.md` | `docs/adr/0089-reference-brownfield-demo.md` | demo manifest, decision checks, reproducibility report | `tests/test_milestone_group7.py` |
| 81 | `docs/phase-81-public-documentation-sdk.md` | `docs/adr/0090-public-sdk-docs.md` | docs index, coverage report, public examples | `tests/test_milestone_group7.py` |
| 82 | `docs/phase-82-conclusion-release-certification.md` | `docs/adr/0091-conclusion-release-certification.md` | certification criteria, blocking findings, evidence-label claims | `tests/test_milestone_group7.py` |

## Shared Contracts

- The TCB is explicit and audited for required categories before certification.
- Every required adversarial threat class has a benchmark-required scenario.
- A reference demo must include accepted and refused requirements.
- Demo reports distinguish missing artifacts, unchecked reports, and decision
  mismatches.
- Public docs are an indexed release artifact tied to real paths, schemas, and
  adopter audiences.
- Conclusion certification consumes reports; it does not create stronger
  evidence than those reports contain.
- Schema freeze is a required release criterion.

## Implemented Schemas

- `schemas/threat-model-report.schema.json`
- `schemas/reference-demo-manifest.schema.json`
- `schemas/reference-demo-report.schema.json`
- `schemas/public-documentation-index.schema.json`
- `schemas/public-documentation-coverage-report.schema.json`
- `schemas/conclusion-certification-report.schema.json`

## Verification Surface

`tests/test_milestone_group7.py` covers:

- complete default TCB and required threat coverage;
- deterministic threat-model findings for missing TCB categories;
- reference demo path, command, and decision checks;
- public docs path, schema, audience, and example coverage;
- certified release output from valid evidence;
- blocked release output from incomplete threat-model and schema-freeze inputs.

## Exit Readiness

Group 7 is ready when the phase specs and ADRs are accepted, the schema-backed
APIs expose each release-hardening contract, the public documentation index
resolves to repository files, and the focused Group G test suite plus schema
drift check pass.
