# ADR 0090: Public SDK, Documentation Versioning, And External Integration Contract

## Status

Accepted

## Context

External adopters need to know which documents, schemas, examples, and CLI
surfaces apply to their role. A documentation index that only lists titles is
not enough for release certification because it can point at missing files or
omit an audience.

The conclusion release needs a stable public adoption surface for users,
adapter authors, backend authors, and operators.

## Decision

Add a `PublicDocumentationIndex` and `PublicDocumentationCoverageReport`.

The index records docs, audiences, paths, schema references, examples, and
coverage tags. The coverage report validates path existence, required audience
coverage, and schema reference availability.

The required audiences are:

- user;
- adapter author;
- backend author;
- operator.

The default index points to:

- `docs/getting-started.md`
- `docs/adapter-sdk-guide.md`
- `docs/formal-backend-guide.md`
- `docs/operator-guide.md`
- `examples/static-adapter-template`
- `examples/ci-gate-template`

## Rationale

Versioning docs as an index lets release certification consume documentation as
evidence without converting prose into the source of truth. Binding docs to
schema names keeps adopters oriented toward the machine-readable contracts.

## Consequences

Positive:

- Public docs become a checkable release artifact.
- Missing audiences, paths, and schema refs are explicit.
- SDK examples are discoverable by stable id.

Negative:

- Docs and schemas must be updated together when contract names change.
- The index does not prove documentation quality; it proves coverage and
  discoverability.

## Alternatives Considered

- Rely on `README.md` as the public documentation. Rejected because one document
  cannot represent all adopter roles or schema bindings cleanly.
- Generate docs entirely from schemas. Rejected because role-specific workflow
  guidance still needs authored context.

## Validation

`tests/test_milestone_group7.py` verifies default audience coverage, doc and
example counts, and blocking behavior for missing docs and schema references.
