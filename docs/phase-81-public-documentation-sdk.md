# Phase 81 - Public Documentation And SDK

## Status

Implemented.

## Purpose

Give external users, adapter authors, backend authors, and operators a stable
map from adoption tasks to versioned docs, examples, and schemas.

The public SDK is deliberately a documentation and contract surface. It does not
change proof semantics. It makes the existing contracts discoverable and
release-checkable.

## Scope

The phase adds:

- public documentation index;
- documentation coverage report;
- getting-started, adapter SDK, backend SDK, and operator docs;
- static adapter and CI gate example templates;
- CLI commands to emit and validate the public docs index.

## Data Contracts

Implementation module: `nlreq.public_sdk`.

Schemas:

- `schemas/public-documentation-index.schema.json`
- `schemas/public-documentation-coverage-report.schema.json`

Primary models:

- `PublicDocumentationIndex`
- `PublicDocEntry`
- `PublicSdkExample`
- `PublicDocumentationCoverageReport`

The required audiences are:

- `user`
- `adapter_author`
- `backend_author`
- `operator`

## API And CLI

Core functions:

- `build_default_public_documentation_index(version="0.1")`
- `validate_public_documentation_index(index, existing_paths, existing_schemas=None)`

CLI:

```bash
uv run nlreq public-docs-index --out /tmp/public-docs.json
uv run nlreq public-docs-check /tmp/public-docs.json --project-root .
```

## Invariants

- Documentation ids and example ids must be unique.
- Every required audience must have at least one doc entry.
- Docs should bind to relevant schemas so adopters can find the machine
  contract behind prose guidance.
- Example templates must declare coverage tags.
- A docs index alone is not enough; path and schema-reference coverage can be
  checked through `public-docs-check`.

## Verification

`tests/test_milestone_group7.py` verifies that the default index covers all
required audiences, examples, and schema refs, and that missing docs or schema
refs block the coverage report.

## Exit Criteria

- Public docs and examples have stable ids.
- External adopters can discover user, adapter, backend, and operator contracts.
- Release certification can reject incomplete public docs.
- The docs index resolves to real repository files.
