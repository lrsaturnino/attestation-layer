# Phase 8 Continuous Attestation

Phase 8 turns package validation from a PR-time check into a repeatable
attestation run over current source, package artifacts, adapter configuration,
and optional normalized traces.

## Implemented Slice

- ADR 0010 design anchor
- `nlreq continuous-attestation` CLI command
- time-indexed continuous attestation run JSON
- Markdown report output
- scheduled/manual/webhook/release trigger metadata
- package-index refresh inside the run artifact
- adapter configuration fingerprints for configured adapter validation
- package freshness summaries, including artifact presence and review age
- previous-run delta detection for:
  - missing packages
  - new packages
  - status regressions
  - validation regressions
  - evidence hash changes
- normalized trace artifact ingestion through the existing
  `NormalizedTraceArtifact` schema
- trace provenance findings for missing requirement ids, unknown requirements,
  missing redaction status, and adapter mismatches
- report-only findings for stale, failed, regressed, contradicted, unsupported,
  or missing evidence

## Run A Continuous Attestation Report

```bash
uv run nlreq continuous-attestation requirements \
  --trigger schedule \
  --run-id RUN-2026-06-01 \
  --repo-ref refs/heads/main \
  --out /tmp/nlreq-continuous.json \
  --markdown-out /tmp/nlreq-continuous.md
```

Adapter-specific packages can be validated during the run by passing the same
adapter options used by package-index, CI report, soft gate, and hard gate:

```bash
uv run nlreq continuous-attestation requirements \
  --python-package-root tests/fixtures/adapters/pythonpkg/samplepkg \
  --package-name samplepkg \
  --project-root . \
  --openapi-document tests/fixtures/adapters/openapi/sample-openapi.json \
  --openapi-name sample-api \
  --json-schema-document tests/fixtures/adapters/jsonschema/sample-schema.json \
  --json-schema-name sample-json-schema \
  --asyncapi-document tests/fixtures/adapters/asyncapi/sample-asyncapi.json \
  --asyncapi-name sample-event-api
```

## Compare Against A Previous Run

```bash
uv run nlreq continuous-attestation requirements \
  --trigger schedule \
  --previous-run /tmp/nlreq-continuous-previous.json \
  --out /tmp/nlreq-continuous-current.json
```

The command reports status regressions and validation regressions as error
findings. Evidence hash changes, new packages, and missing packages are reported
as warning findings by default.

## Ingest Normalized Trace Artifacts

```bash
uv run nlreq continuous-attestation requirements \
  --trace-artifact /tmp/normalized-traces.json \
  --out /tmp/nlreq-continuous-with-traces.json
```

Trace ingestion validates artifact shape and provenance. It does not rewrite
requirement packages and does not claim `TRACE_VALIDATED` unless a future
adapter-specific trace backend defines that evidence contract.

Expected trace metadata:

```json
{
  "requirement_ids": ["REQ-AUTH-001"],
  "environment": "staging",
  "capture_window": {
    "start": "2026-06-01T00:00:00Z",
    "end": "2026-06-01T01:00:00Z"
  },
  "redaction": {
    "status": "redacted"
  }
}
```

## Boundary

Continuous attestation reports around reviewed packages. It does not mutate
`requirement.ir.json`, `review.json`, `evidence.json`, or `status.json`.

The command is report-only. Hard-gate enforcement over continuous-run findings is
left for a later policy extension.

## Validation

```bash
uv run pytest tests/test_continuous.py
uv run nlreq continuous-attestation requirements --trigger manual
```
