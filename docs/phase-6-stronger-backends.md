# Phase 6 Stronger Evidence Backends

Phase 6 adds source-fresh, stronger adapter evidence while preserving the pure
status-decision boundary.

## Implemented Slice

- ADR 0008 design anchor
- counterexample artifact schema
- normalized trace artifact schema
- generated-test artifact schema
- opt-in generated Python property task for supported `succeed` claims
- generated-test provenance in task payloads
- generated-test, counterexample, and normalized-trace package artifacts
- source hashes in Python adapter task inputs
- stale source detection through package validation
- backend counterexample output for generated property failures

## Design Anchor

The stronger evidence backend model is defined in
`docs/adr/0008-phase-6-stronger-evidence-backends.md`.

## Boundary

Generated property evidence is `TEST_VALIDATED`, not a proof. Phase 6 does not
make trace validation gateable by default, add model checking, or change
`decide_status`.

## Validation Plan

```bash
uv run pytest tests/test_python_adapter.py tests/test_python_package.py tests/test_schema.py
uv run nlreq python-package tests/fixtures/requirements/python_operation_success.nlreq --out /tmp/REQ-PY-PROP-001 --requirement-id REQ-PY-PROP-001 --title "Python operation succeeds for approved actor" --claim-kind state_precondition --package-root tests/fixtures/adapters/pythonpkg/samplepkg --package-name samplepkg --project-root . --property-checks
uv run nlreq python-validate /tmp/REQ-PY-PROP-001 --package-root tests/fixtures/adapters/pythonpkg/samplepkg --package-name samplepkg --project-root . --property-checks
```
