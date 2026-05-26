# Phase 3 Adoption Workflow

Phase 3 makes requirement packages usable by other engineers in shadow mode.

## Implemented Slice

- package index generation through `nlreq package-index`
- shadow-mode CI report generation through `nlreq ci-report`
- Markdown CI report output suitable for PR comments or build summaries
- review checklist template generation through `nlreq review-template`
- committed review checklist template in `docs/review-checklist-template.md`
- adapter authoring guide in `docs/adapter-authoring-guide.md`
- requirement authoring guide in `docs/adding-a-requirement.md`
- example catalog in `docs/examples.md`

## Package Index

Generate a deterministic index of package status, evidence summaries, review
state, and artifact hashes:

```bash
uv run nlreq package-index requirements --out requirements/index.json
```

The index validates generic packages with `nlreq validate` semantics. Python
adapter packages can be validated while indexing by supplying adapter settings:

```bash
uv run nlreq package-index requirements \
  --python-package-root tests/fixtures/adapters/pythonpkg/samplepkg \
  --package-name samplepkg \
  --project-root . \
  --test-path tests/fixtures/adapters/pythonpkg
```

If a Python adapter package is found without adapter settings, the index records
validation as `skipped` instead of pretending the package is current.

## CI Reporting

Generate a report-only CI artifact:

```bash
uv run nlreq ci-report requirements \
  --out /tmp/nlreq-ci-report.json \
  --markdown-out /tmp/nlreq-ci-report.md
```

The command reports:

- package validity,
- stale evidence and artifact mismatches,
- unresolved or ambiguous bindings,
- failed checks,
- unsupported claims,
- pending reviews,
- refused package statuses.

The report is shadow-mode by default: it returns success after producing the
report and does not block the build. Downstream CI can decide when to convert
specific findings into soft or hard gates.

Phase 4 starts that conversion with `nlreq soft-gate`; see
`docs/phase-4-soft-gate-pilot.md`.

## Review Checklist

Render a Markdown checklist for a package under review:

```bash
uv run nlreq review-template REQ-AUTH-001
```

The same checklist is committed at `docs/review-checklist-template.md`.

## Validation

```bash
uv run pytest tests/test_cli.py
uv run nlreq package-index requirements
uv run nlreq ci-report requirements
uv run nlreq review-template REQ-AUTH-001
```
