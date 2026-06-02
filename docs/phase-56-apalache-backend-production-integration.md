# Phase 56 - Apalache Backend Production Integration

## Status

Implemented as a production wrapper contract.

## Purpose

Add an Apalache backend path that runs through the model-checker runner and
records command, version, bounds, artifacts, output hashes, and counterexample
metadata.

## Implementation

- `nlreq.formal_backend.ApalacheBackend`
- `nlreq formal-backend-check --backend apalache`
- `schemas/formal-backend-request.schema.json`
- `schemas/formal-backend-response.schema.json`

The backend lowers supported IR v2 fragments to TLA, writes module and config
artifacts, renders the Apalache command, and delegates execution to the
normalized runner. Missing Apalache binaries produce `unsupported` with
`tool_missing: true`. They never produce success.

## Evidence Rules

`BOUNDED_CHECKED` is emitted only for `valid` or `counterexample` results from a
real run. Unsupported, timeout, and invalid results carry no closing assurance
level.

## Exit Criteria

- Apalache appears in `existing_formal_boundaries`.
- Tool-missing behavior is non-approving.
- Output includes command metadata, bounds, module/config hashes, stdout/stderr
  hashes, and counterexample records.
