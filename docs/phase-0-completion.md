# Phase 0 Completion

Phase 0 is complete when the adapter-neutral core can deterministically parse controlled requirements, lower them to typed IR, bind symbols through the generic adapter, run Phase 0 checks, emit complete packages, validate package integrity, and prove committed examples are byte-stable.

## Completed Deliverables

- Build plan: `docs/build-plan.md`
- ADRs: `docs/adr/0001-phase-0-tooling.md` through `docs/adr/0006-phase-1-adapter-selection.md`
- Adapter interface: `docs/adapter-interface.md`
- Controlled-language grammar: `src/nlreq/grammar.lark`
- Parser and IR lowering: `src/nlreq/parser.py`
- Typed models and schemas: `src/nlreq/models.py`, `schemas/`
- Generic symbol-table adapter: `src/nlreq/adapter.py`
- Adapter conformance suite: `src/nlreq/conformance.py`
- Self-consistency and SMT checks: `src/nlreq/smt.py`
- Pure status decision: `src/nlreq/status.py`
- Package writer and validator: `src/nlreq/package.py`
- CLI: `src/nlreq/cli.py`
- Golden package tests: `tests/test_package.py`
- Phase 1 adapter selection: Python package adapter in `docs/adr/0006-phase-1-adapter-selection.md`

## Required Validation

```bash
uv run python scripts/check_schema_drift.py
uv run pytest
uv run nlreq conformance
uv run nlreq validate-all requirements
```

## Phase 0 Package Examples

- `requirements/REQ-AUTH-001`
- `requirements/REQ-STATE-001`
- `requirements/REQ-NUM-001`
- `requirements/REQ-REFUSED-UNBOUND-001`

The first three are the required Phase 0 success examples. The refused package is retained as a negative-path golden fixture for refusal provenance.

## Boundary

Phase 0 intentionally does not include a real target adapter, trace validation, model checking, coverage/freshness gates, or CI adoption workflow. Those begin after the Python package adapter work starts in Phase 1.
