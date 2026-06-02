# Formal Backend Guide

Formal backends consume lowered artifacts and return bounded, unsupported,
timeout, counterexample, or proof-level outcomes through a stable request and
response contract.

## Required Contracts

- `schemas/formal-backend-request.schema.json`
- `schemas/formal-backend-response.schema.json`
- `schemas/model-checker-run.schema.json`
- `schemas/tla-results.schema.json`
- `schemas/proof-evidence-boundary-report.schema.json`

## Evidence Rules

- Record command, arguments, versions, bounds, runtime, and artifact hashes.
- Label bounded checks as bounded evidence only.
- Return `unsupported` for fragments outside the backend contract.
- Normalize counterexamples before they enter product-facing reports.
- Do not allow backend success text alone to upgrade an evidence label.

## Release Use

Conclusion certification consumes benchmark and evidence reports derived from
formal backend output. Backend wrappers remain part of the trusted computing
base and are named in the threat model.
