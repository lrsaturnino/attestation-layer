# ADR 0123: Public SDK And Documentation Freeze

## Status

Accepted

## Context

The public documentation index checks audiences, paths, examples, and schema
references. Before an extended conclusion release, public docs also need
explicit topic coverage, frozen schema hashes, and compatibility commitments.

## Decision

Add `PublicDocumentationFreezeReport`.

The freeze requires coverage for evidence labels, limitations, failure modes,
CLI usage, schema guide, adapter guide, CI modes, and SDK API. It also requires
frozen hashes for referenced schemas and at least one compatibility commitment.

## Rationale

The release claim is public-facing. Users should be able to understand what the
tool proves, what it only checks within bounds, how failures appear, and which
contracts are stable without reading internal source files.

## Consequences

Positive:

- Public docs are checked as release evidence.
- Schema references are hash-frozen.
- Compatibility commitments become machine-readable.

Negative:

- Documentation updates must update the freeze report before certification.

## Validation

`tests/test_milestone_group9.py` verifies topic coverage, schema hash coverage,
and compatibility commitment enforcement.
