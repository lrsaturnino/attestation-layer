# Getting Started

This guide covers the public path for checking one controlled requirement
through the local attestation layer.

## Install

```bash
uv sync --extra dev
```

## Build A Requirement Package

```bash
uv run nlreq package tests/fixtures/requirements/authorization_precondition.nlreq \
  --out /tmp/REQ-AUTH-001 \
  --requirement-id REQ-AUTH-001 \
  --title "Unauthorized operation is rejected before state changes" \
  --claim-kind authorization_precondition
```

## Validate The Package

```bash
uv run nlreq validate /tmp/REQ-AUTH-001
```

The machine-readable artifacts are validated against the JSON Schemas under
`schemas/`. The package is not a proof by itself. It is an input to later
closure, evidence, and CI gate stages.

## Release Inputs

Conclusion certification expects benchmark, threat model, reference demo,
documentation, and schema-freeze evidence. Generate the default public docs
index with:

```bash
uv run nlreq public-docs-index --out /tmp/public-docs.json
uv run nlreq public-docs-check /tmp/public-docs.json --project-root .
```
