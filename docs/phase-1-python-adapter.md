# Phase 1 Python Package Adapter

Phase 1 starts the first real adapter selected in ADR 0006: Python packages.

## Implemented Slice

- Python package source indexing through `ast`
- deterministic module, class, function, and method symbol discovery
- exact-name and suffix-name symbol resolution
- ambiguity detection for duplicate suffix matches
- adapter binding validation against the indexed package symbols
- `STATICALLY_RESOLVED` and `TYPE_CHECKED` evidence capability reporting
- optional `TEST_VALIDATED` capability when scoped pytest paths are configured
- adapter verification tasks for Python symbol-shape checks and scoped pytest evidence
- adapter-side execution for generated symbol-shape and scoped pytest tasks
- adapter conformance coverage through `nlreq.conformance.assert_adapter_conforms`
- CLI conformance command: `nlreq python-conformance`

## Boundary

This slice can run scoped pytest tasks and normalize supplied backend results into
the core `BackendResult` model. Package-level status integration remains outside
this slice because Phase 0 package validation is still generic-adapter based.

Dynamic imports, generated modules, monkeypatching, runtime object introspection, and
coverage/freshness gates remain future Phase 1 or Phase 2 work.

## Validation

```bash
uv run pytest tests/test_python_adapter.py
uv run nlreq python-conformance tests/fixtures/adapters/pythonpkg/samplepkg --package-name samplepkg
```

The committed fixture package exposes:

- `operation`, a resolvable function action
- `actor`, a resolvable function symbol
- `duplicate_symbol`, intentionally defined in two modules to prove ambiguity handling
