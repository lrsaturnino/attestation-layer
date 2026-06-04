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

## Pinned Backend Versions

The model checkers are external binaries, not Python dependencies. They are pinned to exact
versions and verified against a published SHA-256 before use, so every run records a
known-good, reproducible tool. Install both with `scripts/install_formal_backends.sh`, which
downloads each artifact and aborts on a checksum mismatch.

| Backend | Role | Version | Artifact | SHA-256 | Version command |
|---|---|---|---|---|---|
| Apalache (`apalache-mc`) | primary (symbolic) | `0.58.0` | [`apalache-0.58.0.tgz`](https://github.com/apalache-mc/apalache/releases/download/v0.58.0/apalache-0.58.0.tgz) | `55b4da129140b3b6b4106b31eddf36b5f49d896bf2ec8b4cf81c93bc37b9b3d7` | `apalache-mc version` |
| TLC (`tla2tools.jar`) | reserve (explicit-state) | `1.7.4` | [`tla2tools.jar`](https://github.com/tlaplus/tlaplus/releases/download/v1.7.4/tla2tools.jar) | `936a262061c914694dfd669a543be24573c45d5aa0ff20a8b96b23d01e050e88` | `java -cp tla2tools.jar tlc2.TLC` |

The Apalache checksum is cross-verified against the release's official `sha256sum.txt` and the
GitHub release-asset digest. Each backend's version command is recorded with every run
(`FormalBackendExecution.tool_version_command`), so the resolved binary and its reported
version land in the run's reproducibility metadata.

### Tool-unavailable policy

A missing or unresolvable binary degrades to `tool_error` / `UNVERIFIED` — never a silent
`valid`. Tests that exercise a real backend skip with a recorded reason when the binary is
absent (`apalache-mc` not on `PATH`), and CI marks the vertical *tool-unavailable* rather than
passing it. Bounded evidence (`BOUNDED_CHECKED`) is only emitted by a real checker run that
records its bounds, command, and a non-null tool version.

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
