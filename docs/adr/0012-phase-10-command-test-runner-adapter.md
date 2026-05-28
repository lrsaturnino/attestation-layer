# ADR 0012: Phase 10 Command/Test-Runner Adapter

## Status

Proposed

## Context

Phases 0 through 9 establish deterministic requirement packages, adapter
evidence, gates, continuous reports, and agent workflow artifacts. The current
implementation can inspect generic symbol tables, Python packages, and OpenAPI
documents. That is enough for a serious pilot, but many brownfield codebases
will initially contain unsupported languages, frameworks, build systems, and
test runners.

Adding one language adapter per ecosystem would have poor early returns. A
single command/test-runner adapter can cover a much wider set of brownfield
systems by linking reviewed requirements to explicit checks that teams already
trust: pytest, Jest, Vitest, `go test`, `cargo test`, Foundry, Hardhat, shell
scripts, service contract checks, or project-specific validation commands.

This adapter must remain conservative. A passing command can provide
`TEST_VALIDATED` evidence only for the reviewed command, target hashes, and
requirement package it was tied to. It is not proof of semantic correctness and
must not imply that the Attestation Layer understands the target language.

## Decision

Phase 10 will introduce a command/test-runner adapter as the next broad-coverage
adapter family.

The adapter will execute reviewed command checks declared in a package-adjacent
configuration artifact. Each check will include:

- check id and human-readable name,
- requirement ids covered by the check,
- command as an argv array, not a shell string,
- working directory,
- timeout,
- target source paths and test paths,
- expected exit code,
- optional environment allowlist,
- optional output capture limits,
- and evidence level requested.

The adapter will record:

- command argv,
- working directory,
- start and end timestamps,
- exit code,
- timeout status,
- stdout/stderr hashes or bounded excerpts,
- source and test file hashes,
- package hashes,
- tool versions when declared,
- and counterexample or failure diagnostics when available.

The initial adapter will support `TEST_VALIDATED` evidence only when:

- the command exits with the expected code,
- the check is explicitly linked to the requirement id,
- all declared target and test paths are present and hashed,
- the command definition is reviewed or package-associated,
- and the command result is fresh against the current target hashes.

Failed commands produce `REFUSED_FAILED_CHECK` through the existing evidence and
status path. Timeouts produce timeout evidence. Missing commands, missing files,
ambiguous requirement coverage, or stale hashes produce report/gate findings.

The adapter must not:

- infer coverage from command names alone,
- discover and bless tests automatically without reviewed linkage,
- execute shell strings by default,
- allow hidden network or environment dependencies to satisfy gates without
  policy,
- rewrite reviewed requirement packages in place,
- bypass adapter conformance,
- or claim `TRACE_VALIDATED`, `BOUNDED_CHECKED`, or `PROVEN_INDUCTIVE`.

## Artifact Shape

The planned check configuration shape is:

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

The planned result artifact shape is:

```json
{
  "schema_version": "0.1",
  "adapter": "command",
  "results": [
    {
      "check_id": "CHK-AUTH-UNAUTHORIZED",
      "requirement_ids": ["REQ-AUTH-001"],
      "status": "valid",
      "evidence_level": "TEST_VALIDATED",
      "exit_code": 0,
      "timed_out": false,
      "target_hashes": {
        "src/auth.py": "sha256:..."
      },
      "test_hashes": {
        "tests/test_auth.py": "sha256:..."
      },
      "stdout_hash": "sha256:...",
      "stderr_hash": "sha256:..."
    }
  ]
}
```

Exact filenames and schema names may change during implementation, but the
contract must remain deterministic and hash-addressed.

## Consequences

The command adapter gives high Pareto value because it can produce useful
evidence for many brownfield systems before specialized adapters exist. It also
fits the Phase 9 agent workflow: failed commands naturally become retry payloads
with command ids, output hashes, target paths, and minimal diagnostics.

The tradeoff is weaker semantic understanding. A passing command means only that
the reviewed command passed under recorded inputs. It does not prove the
implementation satisfies the requirement outside the command's exercised scope.

This is acceptable because the Attestation Layer's core principle is evidence
honesty. The adapter improves coverage without pretending to be a universal
language inspector.
