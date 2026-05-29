# Phase 2 Python Evidence Packages

Phase 2 begins stronger evidence backends for the selected Phase 1 adapter:
Python packages.

## Implemented Slice

- Python-adapter package generation through `nlreq python-package`
- Python-adapter package validation through `nlreq python-validate`
- `adapter-results.json` artifact for normalized adapter backend results
- committed `backend-results.schema.json`
- package evidence claims for:
  - Python static symbol resolution
  - core self-consistency
  - core SMT supported-claim checking
  - Python symbol-shape validation
  - scoped pytest validation
- freshness checks tying adapter results to verification-task input hashes
- pure status decisions over the combined core and adapter evidence object

## Boundary

This slice validates scoped pytest results as package evidence, but it does not
generate tests, infer coverage, normalize runtime traces, parse counterexamples,
or integrate CI reporting. Those remain Phase 2 follow-on work.

Existing Phase 0 generic packages remain validated by `nlreq validate` and
`nlreq validate-all`; Python-adapter packages use `nlreq python-validate` because
their task integrity depends on the selected Python package adapter configuration.

## Validation

```bash
uv run pytest tests/test_python_package.py
uv run nlreq python-package tests/fixtures/requirements/python_operation_success.nlreq \
  --out /tmp/REQ-PY-001 \
  --requirement-id REQ-PY-001 \
  --title "Python operation succeeds for approved actor" \
  --claim-kind state_precondition \
  --package-root tests/fixtures/adapters/pythonpkg/samplepkg \
  --package-name samplepkg \
  --project-root . \
  --test-path tests/fixtures/adapters/pythonpkg

uv run nlreq python-validate /tmp/REQ-PY-001 \
  --package-root tests/fixtures/adapters/pythonpkg/samplepkg \
  --package-name samplepkg \
  --project-root . \
  --test-path tests/fixtures/adapters/pythonpkg
```
