# ADR 0053: End-to-End Requirement Gate Contract

## Status

Proposed

## Context

The Attestation Layer now has separate components for parsing, translation
agreement, self-consistency, source impact, coverage, trace replay, delta
extraction, proof closure, and closure gating. Product use needs one action
surface that runs those components together and returns a single decision
without discarding the intermediate evidence.

## Decision

Introduce an end-to-end requirement gate report and a `requirement-gate` CLI.

The gate:

- parses controlled text into IR v2;
- creates a deterministic translation agreement artifact;
- lowers to the formal target;
- runs requirement self-consistency;
- extracts source traces;
- runs source impact and impact v2;
- checks spec coverage and trace alignment;
- runs trace replay;
- checks system consistency;
- extracts deltas;
- builds a proof object;
- evaluates the closure gate.

The final report returns:

- `decision`: `accepted`, `refused`, or `unknown`;
- `downstream_action_allowed`: true only for accepted;
- proof and closure status;
- per-stage statuses;
- structured blockers;
- content-hashed references to all intermediate artifacts.

## Consequences

Consumers get one stable action API and a complete audit trail. A downstream
action no longer has to stitch together multiple reports and guess whether
missing evidence is acceptable.

The gate remains an orchestrator. Individual components keep their own schemas,
tests, and semantics.
