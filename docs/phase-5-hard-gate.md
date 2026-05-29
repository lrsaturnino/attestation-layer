# Phase 5 Hard Gate Opt-In

Phase 5 converts proven soft-gate policy into scoped blocking CI behavior.

## Implemented Slice

- gate policy artifact
- waiver artifact
- hard-gate command or hard-gate mode over `nlreq soft-gate`
- scoped enforcement by adapter, package root, requirement id, or changed path
- deterministic pass/fail exit behavior
- JSON and Markdown hard-gate reports
- stale and expired waiver detection
- tests for allowed, blocked, waived, stale-waiver, expired-waiver, and
  out-of-scope paths

## Design Anchor

The gate policy and waiver model is defined in
`docs/adr/0007-gate-policy-and-waiver-model.md`.

Example artifacts:

- `docs/examples/gate-policy.example.json`
- `docs/examples/waiver.example.json`

## Policy Shape

A policy should answer four questions:

1. Which packages or requirement ids are in scope?
2. Which adapters and changed paths are in scope?
3. Which statuses, review decisions, and evidence levels are acceptable?
4. Which findings are blocking versus report-only?

The default hard-gate policy should be narrow. New adapters and new evidence
backends remain report-only until they show low false-positive rates in soft
gate.

## Waiver Shape

A waiver is a temporary, reviewed exception. It must include:

- requirement id or package path,
- reviewer,
- reason,
- expiration,
- reviewed package hashes,
- linked issue or PR.

Expired waivers and waivers whose reviewed hashes no longer match the package
must be ignored by hard-gate enforcement.

## Boundary

Phase 5 does not add new evidence backends, generate tests, normalize traces, or
expand adapters. Those remain Phase 6 and Phase 7 work.

Phase 5 must not change `decide_status`; enforcement remains a Layer 7 operation
over already-computed package artifacts.

## Validation Plan

```bash
uv run pytest tests/test_cli.py
uv run nlreq soft-gate requirements --requirement-id REQ-AUTH-001
uv run nlreq soft-gate requirements --requirement-id REQ-REFUSED-UNBOUND-001 --fail-on-blocking
uv run nlreq hard-gate requirements --policy docs/examples/gate-policy.example.json --requirement-id REQ-AUTH-001 --changed-path src/auth.py
uv run nlreq hard-gate requirements --policy docs/examples/gate-policy.example.json --requirement-id REQ-REFUSED-UNBOUND-001 --changed-path src/auth.py
```

The refused-package soft-gate and hard-gate commands are expected to exit
non-zero; they prove the blocking paths are active.
