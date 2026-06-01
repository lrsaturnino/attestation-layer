# ADR 0039: Model-Checker Runner Contract

## Status

Proposed

## Context

Earlier phases established formal backend and proof closure boundaries, but the
default backend path still distinguished shape checks from real tool execution.
The roadmap requires bounded verification to be backed by an actual command run
with explicit budgets, normalized results, and reproducibility metadata.

Different tools report success, unsupported fragments, counterexamples,
timeouts, and infrastructure failures differently. Without a shared runner,
each backend would duplicate subprocess handling and risk hiding timeouts or
command failures behind backend-specific green statuses.

## Decision

Introduce a schema-backed model-checker runner contract.

The runner accepts:

- a checker id and run id;
- an argv command and working directory;
- timeout, depth, state, memory, and solver-option budgets;
- expected exit code;
- optional tool-version metadata or a version command;
- output truncation limits.

The runner emits one normalized result with:

- outcome: `valid`, `counterexample`, `timeout`, `unsupported`, or
  `tool_error`;
- exit code and timeout flag;
- stdout/stderr hashes plus bounded tails;
- normalized counterexample excerpts for common violation markers;
- unsupported markers;
- executable, command line, cwd, tool version, and budget metadata.

The runner classifies timeout, unsupported, and tool-error outcomes as
non-approving. It does not emit `BOUNDED_CHECKED` or `PROVEN_INDUCTIVE` evidence
directly; backend and producer policy layers must decide evidence semantics.

## Consequences

Backends can consume one execution primitive instead of each implementing
subprocess behavior. Reproducibility metadata becomes consistent before the
first real TLA+ backend is introduced.

The marker taxonomy is intentionally conservative and will need tool-specific
parsers as Apalache, TLC, TLAPS, Alloy, Lean, or other backends are added. Until
those parsers exist, unknown non-zero exits remain tool errors, and outputs that
do not match success or failure markers are valid only when the command exits
with the expected code.
