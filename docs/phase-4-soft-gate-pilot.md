# Phase 4 Soft Gate Pilot

Phase 4 turns shadow-mode adoption reports into an opt-in soft gate for
implementation workflows.

## Implemented Slice

- soft-gate report generation through `nlreq soft-gate`
- requirement reference input through repeated `--requirement-id`
- requirement reference extraction from PR body or commit-message files through
  `--references-file`
- JSON and Markdown report output
- report-only default exit behavior
- explicit non-zero exit behavior through `--fail-on-blocking`
- validation that referenced requirements exist, validate cleanly, have approved
  review state, and are accepted for implementation

## Soft Gate Behavior

By default, the command reports blockers without failing the process:

```bash
uv run nlreq soft-gate requirements --requirement-id REQ-AUTH-001
```

For CI jobs that should fail on blockers:

```bash
uv run nlreq soft-gate requirements \
  --references-file /tmp/pr-body.md \
  --out /tmp/nlreq-soft-gate.json \
  --markdown-out /tmp/nlreq-soft-gate.md \
  --fail-on-blocking
```

The gate blocks when:

- no requirement reference is present,
- a referenced requirement package is unknown,
- a referenced package fails validation,
- a referenced package has no status,
- a referenced package status is not accepted,
- a referenced package review is not approved,
- a referenced package has pending review evidence.

Unsupported claims on referenced packages are reported as warnings so teams can
observe noise before promoting a policy to a hard gate.

## CI Integration

A soft-gate CI job should pass a PR body, commit message, or release note file to
`--references-file`. The command extracts requirement ids matching `REQ-...`.

Start without `--fail-on-blocking` when introducing the workflow. Add
`--fail-on-blocking` only after the team agrees that every implementation PR must
reference an accepted requirement package.

## Validation

```bash
uv run pytest tests/test_cli.py
uv run nlreq soft-gate requirements --requirement-id REQ-AUTH-001
uv run nlreq soft-gate requirements --requirement-id REQ-REFUSED-UNBOUND-001
uv run nlreq soft-gate requirements --fail-on-blocking
```
