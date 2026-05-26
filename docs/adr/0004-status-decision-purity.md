# ADR 0004: Status Decision Purity

## Status

Accepted

## Context

The system needs a trustworthy final status for each requirement package. If status decision logic performs file writes, tool calls, or network effects, it becomes hard to test and audit.

## Decision

The status decision layer is a pure function:

```text
evidence + required levels + review state + freshness state -> status + reason + next actions
```

It must not write files, call verification tools, post comments, or mutate state. Package emission and CI reporting happen after the status is computed.

## Consequences

Status behavior can be covered by golden tests. Given the same input evidence object, the system must always return the same status.
