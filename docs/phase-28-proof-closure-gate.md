# Phase 28 Proof Closure Gate

Phase 28 turns the prior evidence pipeline into an explicit proof closure
artifact. It aggregates premise routes, backend results, producer permissions,
coverage status, and trace-alignment status into one object that downstream
automation can require before acting.

This phase does not add a new proof backend. It prevents existing boundary
checks, drafts, traces, or LLM output from being mistaken for closed proof.

## Purpose

The phase lets the Attestation Layer say:

```text
Every proof fragment for the requirement was routed to an allowed evidence
producer, the required result was present, spec coverage and trace alignment
passed, and the resulting proof object is closed.
```

It does not say:

```text
The TLA boundary is an inductive proof.
Trace alignment proves the requirement.
An LLM or draft artifact can emit high-assurance evidence.
```

## Implementation Scope

Phase 28 implementation should include:

- proof dispatch plan for compositional IR proof fragments;
- evidence producer mapping with allowed evidence levels;
- proof object aggregation over backend results, spec coverage, and trace
  alignment;
- closure gate report for downstream actions such as merge or backlog promotion;
- reproducibility metadata and input hashes;
- JSON schemas and CLI commands;
- tests for closed proof objects, blocked context, invalid producer mappings,
  and gate behavior.

## Evidence Semantics

Backend results discharge proof fragments only when:

- the backend result is `valid`;
- the result declares the exact evidence level required by the route;
- the producer is registered in the evidence producer mapping;
- the producer is allowed to emit that evidence level;
- high-assurance evidence is emitted only by a real producer;
- and spec coverage plus trace alignment both pass.

`needs_review`, `unsupported`, `timeout`, `counterexample`, missing context, and
invalid producer mappings are non-closing states.

## Success Criterion

Phase 28 succeeds when:

- requirement proof fragments are routeable to a backend;
- one aggregated proof object records discharged and open premises;
- downstream closure is blocked unless the proof object is closed;
- high-assurance levels cannot be emitted by placeholders or drafting tools;
- and proof artifacts are schema-backed and reproducible.

## Boundary

This phase is not a new Apalache, TLC, SMT, or proof-assistant integration. It
is the closure layer that records and enforces the evidence produced by those
systems when they exist.
