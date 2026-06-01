# Phase 30 Real Model-Checker Runner

Phase 30 introduces the first execution boundary for real verification tools. It
does not decide which formal target is authoritative. It gives later formal
backends one normalized way to run a local checker, record the budget, classify
the outcome, and preserve enough metadata to reproduce the run.

## Purpose

The phase lets the Attestation Layer say:

```text
This checker command ran with this budget, produced this output, and was
classified as valid, counterexample, timeout, unsupported, or tool error.
```

It does not say:

```text
The requirement is proven inductively.
The model checker semantics match every formal backend.
The command output is trusted without a registered producer policy.
```

## Implementation Scope

Phase 30 implementation includes:

- model-checker budget model for timeout, depth, states, memory, and solver
  options;
- command request model with checker id, run id, working directory, expected
  exit code, output limit, and optional tool-version metadata;
- normalized result artifact with stdout/stderr hashes and bounded tails;
- outcome classification for valid, counterexample, timeout, unsupported, and
  tool-error results;
- counterexample excerpts for common model-checker violation markers;
- CLI command for running an arbitrary local checker command;
- JSON schemas and tests.

## Evidence Semantics

The runner is an execution primitive, not a proof producer by itself. A `valid`
runner outcome can support bounded evidence only when a later backend binds the
command to a formal artifact, records the bounds, and maps the checker identity
through producer policy.

Timeout, unsupported, and tool-error outcomes never approve. Counterexample
outcomes are failure evidence and must remain visible to proof closure and delta
reporting.

## Success Criterion

Phase 30 succeeds when:

- a real local checker command can run from the CLI;
- results include exact command, cwd, tool-version field, and budget metadata;
- stdout and stderr are hash-addressed with bounded tails;
- counterexample artifacts are normalized;
- timeout and tool-error outcomes cannot be classified as valid.

## Boundary

This phase is not a runnable TLA+ backend, not solver-backed `S and R`, and not
producer trust enforcement. Those are strengthened in later phases by consuming
the runner result instead of duplicating subprocess behavior.
