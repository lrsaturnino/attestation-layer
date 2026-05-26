# ADR 0010: Phase 8 Continuous Attestation

## Status

Accepted

## Context

Phases 0 through 7 make requirement packages reviewable, adapter-neutral, and
gateable at PR time. That is not enough after merge. Source code, tests,
OpenAPI documents, generated tasks, and runtime behavior can drift without a new
implementation PR touching the requirement package that originally justified the
change.

Phase 8 needs continuous evidence refresh without weakening the package model.
The reviewed requirement package must remain an auditable artifact. Scheduled
jobs may recompute evidence and report degradation, but they must not silently
rewrite reviewed package contents or inflate runtime observations into proof.

Continuous attestation also introduces operational risks that were not present
in PR-time validation:

- production traces may contain sensitive data,
- scheduled checks may be flaky or environment-dependent,
- evidence trends can be useful without being gate-worthy,
- stale evidence should be reported without mutating historical reviews,
- and teams need a way to evolve requirements when observed behavior shows the
  reviewed spec is incomplete or wrong.

## Decision

Phase 8 will introduce continuous attestation as a report-producing workflow over
existing requirement packages, adapters, and evidence contracts.

The workflow will add time-indexed attestation run artifacts. A run artifact will
record:

- run id,
- trigger type such as schedule, manual, webhook, or release,
- timestamp,
- repository ref and source hashes,
- package root and package ids included in the run,
- adapter configuration fingerprints,
- validation results for each package,
- recomputed verification-task input hashes,
- backend evidence snapshots,
- trace artifact references when trace validation is enabled,
- freshness and age metadata,
- deltas from the previous comparable run,
- and findings for stale, regressed, contradicted, unsupported, or missing
  evidence.

Requirement packages remain immutable unless a human-reviewed requirement
evolution workflow creates a new package revision. Continuous runs may reference
packages and compare their current recomputed evidence with committed artifacts,
but they must not rewrite `requirement.ir.json`, `review.json`, `evidence.json`,
or `status.json` in place.

Runtime trace ingestion will use normalized trace artifacts, not raw production
payloads. Trace artifacts must carry provenance, redaction status, source hash or
trace hash, capture window, environment, adapter id, and requirement ids. Raw
trace storage, PII handling, and retention are outside the package artifact
format and must be controlled by deployment policy.

Evidence levels remain conservative:

- scheduled package validation may refresh `TYPE_CHECKED`,
  `STATICALLY_RESOLVED`, `CONSISTENCY_CHECKED`, `SMT_CHECKED`, and existing
  adapter evidence levels;
- generated or scoped tests may satisfy `TEST_VALIDATED` only when they actually
  ran and passed in the recorded run environment;
- trace checks may satisfy `TRACE_VALIDATED` only when they validate a
  normalized trace artifact against a documented adapter contract;
- mutation testing and seeded-fault runs are specification-quality metrics, not
  evidence levels, until a later ADR defines a gateable backend contract;
- bounded model checking and inductive proof claims remain unavailable unless a
  real backend produces `BOUNDED_CHECKED` or `PROVEN_INDUCTIVE`.

`decide_status` remains pure. Continuous attestation will compute reports and
alerts around evidence objects and package summaries, but it will not add hidden
side effects to status calculation. Hard gates may later opt into continuous-run
findings as policy inputs, but the default Phase 8 posture is report-only.

Phase 8 will also introduce an attestation artifact catalog. The catalog will
describe supported artifact kinds, required provenance fields, freshness rules,
retention expectations, privacy constraints, and which artifacts may satisfy
which evidence levels.

The initial Phase 8 slice will prioritize:

- scheduled package-index refresh,
- source/test/package freshness reports,
- normalized trace artifact ingestion for one supported adapter path,
- evidence trend reports,
- stale or regressed evidence alerts,
- and documentation for operating continuous attestation safely.

## Consequences

Continuous attestation can detect post-merge evidence degradation without waiting
for a new implementation PR. Teams get a durable timeline of package validity,
freshness, adapter results, trace coverage, and evidence regressions.

The tradeoff is operational complexity. Continuous runs need stable
environments, explicit retention policy, trace redaction, and careful alert
tuning. Reports may identify risk before there is enough evidence to block a
release, so Phase 8 keeps enforcement separate from observation by default.

The requirement package remains the human-reviewed anchor. When continuous
evidence shows that a requirement is stale, incomplete, or contradicted, the
system should create a reviewable follow-up package or requirement revision
rather than editing historical artifacts in place.
