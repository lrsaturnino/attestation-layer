# ADR 0006: Phase 1 Adapter Selection

## Status

Accepted

## Context

Phase 1 must choose one real adapter after the Phase 0 core is working. Choosing too early risks letting one ecosystem distort the core architecture.

## Decision

Phase 1 will implement a Python package adapter.

Selected ecosystem: Python packages.

Rationale:

- the Phase 0 core is itself a Python package, so the adapter can dogfood this repository;
- Python has a clear symbol model through modules, classes, functions, and import paths;
- the project already uses `uv`, `pytest`, and generated schemas;
- adapter work can start without network services, chain nodes, or external project setup;
- the result remains general-purpose because Python is only the first adapter, not a core dependency.

Expected adapter-specific tooling:

- Python `ast` and `inspect` for symbol discovery where source is available;
- importlib metadata for package/module resolution;
- `pytest` for test-backed evidence;
- optional `coverage.py` and `hypothesis` after the first adapter slice works.

Evidence types targeted in Phase 1:

- `STATICALLY_RESOLVED` for import/module/function/class symbols;
- `TYPE_CHECKED` for package and symbol shape validation;
- `TEST_VALIDATED` for adapter-provided pytest results.

Reviewer availability:

- initial review can be performed by a Python-capable project reviewer;
- if the author and reviewer are the same person, the review must follow the self-audit rule from the build plan.

Known setup risks:

- dynamic imports and monkeypatching can make symbol discovery incomplete;
- generated modules may not have stable source locations;
- test evidence can be slow or environment-dependent unless invocation is tightly scoped.

## Consequences

Phase 0 remains adapter-neutral. Phase 1 starts with a real adapter that can be tested against this repository before broader ecosystem adapters are attempted.
