# Phase 10 Command/Test-Runner Adapter

Phase 10 should add the smallest high-return adapter for brownfield projects: a
command/test-runner adapter that links reviewed requirements to explicit
project checks.

This phase is implemented in the reference CLI as `command-package`,
`command-validate`, `command-evidence`, and `command-conformance`.

## Purpose

The adapter should let a requirement package say:

```text
This requirement is backed by this exact command,
run from this directory,
against these source and test hashes,
with this timeout and expected exit code.
```

That gives teams useful `TEST_VALIDATED` evidence without building a full
language adapter for every ecosystem.

## Why This Comes Next

The current implementation already has:

- deterministic package artifacts,
- Python and OpenAPI adapters,
- hard/soft gates,
- continuous reports,
- and agent handoff payloads.

The next bottleneck is brownfield coverage. Most existing systems already have
some executable checks, even when they do not have a dedicated Attestation Layer
adapter. A command/test-runner adapter can reuse those checks while preserving
the evidence boundary.

## Planned CLI Shape

Example package build:

```bash
uv run nlreq command-package tests/fixtures/requirements/authorization_precondition.nlreq \
  --out /tmp/REQ-AUTH-CMD-001 \
  --requirement-id REQ-AUTH-CMD-001 \
  --title "Unauthorized operation is rejected" \
  --claim-kind authorization_precondition \
  --checks docs/examples/command-checks.example.json
```

Example package validation:

```bash
uv run nlreq command-validate /tmp/REQ-AUTH-CMD-001 \
  --checks docs/examples/command-checks.example.json
```

Example direct evidence run:

```bash
uv run nlreq command-evidence requirements \
  --checks docs/examples/command-checks.example.json \
  --requirement-id REQ-AUTH-001 \
  --out /tmp/nlreq-command-results.json
```

The implementation keeps command execution explicit through argv arrays and
project-root-relative path hashing.

## Planned Check Config

```json
{
  "schema_version": "0.1",
  "adapter": "command",
  "checks": [
    {
      "check_id": "CHK-AUTH-UNAUTHORIZED",
      "name": "Unauthorized request is rejected",
      "requirement_ids": ["REQ-AUTH-001"],
      "command": [
        "uv",
        "run",
        "pytest",
        "tests/test_auth.py::test_rejects_unauthorized"
      ],
      "cwd": ".",
      "timeout_seconds": 60,
      "expected_exit_code": 0,
      "target_paths": ["src/auth.py"],
      "test_paths": ["tests/test_auth.py"],
      "requested_evidence": "TEST_VALIDATED"
    }
  ]
}
```

Commands must be argv arrays, not shell strings. This keeps execution
inspectable and avoids hidden shell behavior.

## Evidence Semantics

The adapter may produce `TEST_VALIDATED` only when:

- the command exits with the expected code,
- the check explicitly names the requirement id,
- target and test files are present and hashed,
- the command result is fresh for those hashes,
- and the check definition is part of the reviewed or configured workflow.

The adapter must not claim:

- `TRACE_VALIDATED`,
- `BOUNDED_CHECKED`,
- `PROVEN_INDUCTIVE`,
- or implementation correctness outside the command's exercised scope.

## Failure Semantics

The adapter should classify failures into existing evidence/status paths:

| Condition | Result |
|---|---|
| Non-zero unexpected exit | failed check |
| Timeout | timeout evidence |
| Missing command config | package or gate finding |
| Missing target/test file | stale or invalid evidence |
| Requirement id not covered | unsupported or missing evidence |
| Output too large | bounded hash plus diagnostic finding |

Agent retry payloads should include the check id, command argv, target paths,
exit code, timeout status, and bounded diagnostics. They should not instruct a
coder agent to weaken or bypass the requirement.

## Package Artifacts

The phase should add package artifacts such as:

```text
command-checks.json
command-results.json
adapter-results.json
counterexamples.json
evidence.json
status.json
```

The exact filenames should be finalized during implementation, but every
artifact must be reproducible, schema-validated, and hash-addressed where it
affects evidence.

## Safety Rules

- No shell execution by default.
- No implicit network access as gateable evidence unless policy allows it.
- No unbounded stdout/stderr storage.
- No secret environment capture.
- No automatic test discovery treated as reviewed coverage.
- No mutation of reviewed requirement packages in place.
- No passing conformance, no gateable adapter evidence.

## Success Criterion

Phase 10 succeeds when a requirement package can be backed by one or more
reviewed command checks, and:

- command checks produce deterministic result artifacts;
- passing checks can satisfy `TEST_VALIDATED`;
- failed checks and timeouts become structured evidence;
- stale target/test hashes are detected;
- soft and hard gates can consume command evidence;
- continuous attestation can rerun command evidence on a schedule;
- agent verifier handoffs can turn command failures into retry payloads;
- and existing generic, Python, and OpenAPI packages continue to validate
  unchanged.

## Boundary

This phase does not replace language adapters. It gives broad brownfield
coverage while specialized adapters continue to provide deeper symbol and
semantic understanding where that depth is worth the implementation cost.
