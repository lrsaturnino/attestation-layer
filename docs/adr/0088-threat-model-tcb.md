# ADR 0088: Threat Model, TCB Boundary, And Adversarial Evidence Policy

## Status

Accepted

## Context

Conclusion certification needs a defensible security boundary. Earlier phases
produce parsers, translators, formal backend wrappers, source adapters, trace
producers, evidence stores, signatures, CI gates, and human review artifacts.
Without a named trusted computing base, a release could imply stronger evidence
than the system actually has.

The conclusion roadmap also requires benchmark accountability for adversarial
cases. A threat model that names risks only in prose is not enough; the release
pipeline must be able to reject incomplete threat coverage.

## Decision

Publish a machine-readable `ThreatModelReport` as the Phase 79 release security
artifact.

The report records:

- TCB components with category, trust assumption, and failure impact;
- threat scenarios with affected TCB components, mitigations, residual risk, and
  benchmark-required flags;
- release security checklist items;
- explicit release claim boundaries;
- deterministic audit findings.

The required TCB categories are parser, IR validator, translator, formal
backend, source adapter, trace producer, artifact store, producer registry, CI
gate, and human review.

The required threat classes are spoofing, tampering, replay, prompt injection,
stale specs, forged evidence, and malicious adapters. Every required threat
class must have benchmark-required coverage.

## Rationale

The attestation layer is an evidence pipeline. Its security claims depend on
both deterministic tooling and reviewed human decisions. Making the TCB
explicit prevents later certification from silently relying on unstated trust.

Treating benchmark coverage as part of the threat model forces adversarial
scenarios into repeatable evaluation rather than one-off review notes.

## Consequences

Positive:

- Release certification can fail incomplete threat models deterministically.
- Security reviewers can inspect trust assumptions and residual risks.
- Benchmark authors have a stable list of adversarial classes to cover.

Negative:

- The default threat model must be maintained as new trusted components are
  added.
- The report documents residual risk; it does not eliminate that risk.

## Alternatives Considered

- Keep threat modeling as prose documentation. Rejected because certification
  needs machine-readable blocking criteria.
- Require external security-audit tooling before certification. Deferred because
  the first conclusion release needs a stable local contract before external
  integrations.

## Validation

`tests/test_milestone_group7.py` verifies default TCB completeness, required
threat coverage, benchmark-required adversarial scenarios, and deterministic
findings for incomplete TCB reports.
