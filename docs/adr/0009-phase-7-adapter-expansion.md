# ADR 0009: Phase 7 Adapter Expansion

## Status

Accepted

## Context

The core package, evidence, status, soft-gate, hard-gate, and stronger-evidence
contracts have been exercised with the generic adapter and the Python package
adapter. Phase 7 needs a second real adapter to prove that these contracts are
not Python-specific.

The second adapter should expand the target ecosystem without forcing a large
runtime dependency, a non-deterministic toolchain, or cross-system verification
before single-adapter behavior is trustworthy.

Candidate adapters included TypeScript, Go, OpenAPI, smart contracts, and
spec-only systems. The first Phase 7 adapter should be deterministic, easy to
fixture in-repo, and different enough from Python source inspection to exercise
adapter-neutral package validation.

## Decision

Phase 7 will add an OpenAPI adapter as the second real adapter.

The OpenAPI adapter will resolve requirement terms against an OpenAPI document:

- paths,
- operations,
- operation ids,
- parameters,
- request schemas,
- response schemas,
- and security requirements.

The adapter will initially provide:

- symbol discovery from OpenAPI JSON or YAML,
- deterministic binding validation,
- adapter conformance coverage,
- verification tasks for operation shape and declared security requirements,
- backend results normalized through existing `BackendResult`,
- package generation and validation commands,
- package-index and gate compatibility through the existing package summary
  contract,
- and documentation for unsupported OpenAPI constructs.

The first supported claim shapes will be narrow and request-oriented:

```text
if actor is not authorized
then operation must be rejected before state_change
```

and:

```text
if actor is approved
then operation must succeed
```

OpenAPI evidence will be conservative. Schema and security declaration checks
may satisfy `STATICALLY_RESOLVED` or `TYPE_CHECKED`. They must not claim
`TEST_VALIDATED`, `TRACE_VALIDATED`, `BOUNDED_CHECKED`, or `PROVEN_INDUCTIVE`
unless a real backend later supplies that evidence.

Cross-adapter requirements remain out of scope for Phase 7. The OpenAPI adapter
may reference implementation packages only as metadata; it must not claim that a
Python implementation satisfies an OpenAPI requirement unless a later
cross-adapter workflow defines that contract.

## Consequences

Phase 7 can prove adapter neutrality with a second ecosystem while keeping the
implementation small and deterministic. The OpenAPI adapter exercises
non-Python symbol binding, package validation, evidence normalization, and gate
reporting without introducing runtime trace validation or service execution.

The tradeoff is that OpenAPI evidence is weaker than runtime service evidence.
That is acceptable for Phase 7 because the goal is adapter expansion, not
end-to-end service verification. Stronger OpenAPI evidence can be added later
through contract tests, runtime traces, or service-specific adapters.
