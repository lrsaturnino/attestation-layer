# Milestone Group 6 Evidence Integrity, Scale, CI, And Benchmarks Digest

Milestone group 6 is group F from `docs/nl-attestation-conclusion-roadmap.md`,
covering phases 73 through 78. It starts after brownfield grounding, production
adapters, certification, and cross-language proof-object aggregation are present.

## Roadmap Digest

Group 6 turns proof closure from a local computation into an engineering control
that can survive normal delivery workflows. A closure decision is useful only if
its evidence can be resolved later, checked for tampering, surfaced in CI,
measured against public benchmarks, reused safely when inputs have not changed,
and governed with visible exceptions when staged adoption requires temporary
waivers.

The group does not add new semantic proof power. It hardens the evidence and
workflow boundary around the proof power already produced by earlier phases.

## Phase Map

| Phase | Theme | Primary implementation |
|---:|---|---|
| 73 | Evidence artifact store | `nlreq.artifact_store`, `artifact-put`, `artifact-get`, replay bundle manifest |
| 74 | Signed evidence and producer attestation | `nlreq.signed_evidence`, producer key registry, `sign-evidence`, `verify-evidence` |
| 75 | CI and PR action gate | `nlreq.ci_pr_gate`, JSON report, Markdown renderer, hard/report-only modes |
| 76 | Benchmark evaluation | `nlreq.benchmark_reporting`, category counts, false-closure budget |
| 77 | Performance and caching | `nlreq.verification_cache`, hash-keyed cache records, lookup semantics |
| 78 | Policy and waiver governance | `nlreq.policy_governance`, waiver audit, expiration and policy enforcement |

## Shared Contracts

- Content hashes use `sha256:` prefixes and bind reports to retained artifacts.
- JSON reports are authoritative. Markdown, comments, and dashboards are derived
  renderings.
- Cached artifacts remain evidence of prior computation only when all cache-key
  inputs match. Cache hits never increase the evidence label.
- Signature verification proves payload integrity and registered producer
  identity, not semantic correctness.
- Waivers are audit findings. They cannot silently convert a blocked proof into
  a closed proof.
- False closure is the most important benchmark failure mode and can be budgeted
  at zero for hard-gated cases.

## Implemented Schemas

- `schemas/artifact-store-manifest.schema.json`
- `schemas/artifact-lookup-result.schema.json`
- `schemas/replay-bundle-manifest.schema.json`
- `schemas/signed-evidence-envelope.schema.json`
- `schemas/producer-key-registry.schema.json`
- `schemas/signature-verification-report.schema.json`
- `schemas/ci-pr-gate-report.schema.json`
- `schemas/benchmark-evaluation-report.schema.json`
- `schemas/verification-cache-key.schema.json`
- `schemas/verification-cache-index.schema.json`
- `schemas/verification-cache-lookup.schema.json`
- `schemas/gate-policy.schema.json`
- `schemas/waiver.schema.json`
- `schemas/waiver-audit-report.schema.json`

## Verification Surface

`tests/test_milestone_group6.py` covers the group-level guarantees:

- retained artifact lookup, missing-artifact behavior, and replay export;
- signature verification, tamper detection, and high-assurance trusted-key mode;
- report-only and hard-gate CI outcomes;
- benchmark false-closure budget failure;
- cache invalidation across tool versions and policy hashes;
- waiver audit enforcement for expiration, policy duration, reviewed hashes, and
  hard-gate safety.

## Exit Readiness

Group 6 is ready when each phase spec and ADR is versioned, the schema-backed
APIs expose the milestone behavior, and the focused group test suite passes.
The remaining conclusion-roadmap phases can then consume group 6 reports as
auditable release inputs instead of relying on transient CLI output.
