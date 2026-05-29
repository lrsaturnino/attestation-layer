# Adding A Requirement

This workflow adds a requirement package while keeping review and evidence
artifacts reproducible.

## 1. Write Controlled Text

Create a `.nlreq` file using the controlled grammar:

```text
For every operation request:
if actor is approved
then operation must succeed.
```

Use one of the supported claim kinds:

- `authorization_precondition`
- `state_precondition`
- `state_postcondition`
- `numeric_invariant`

## 2. Build The Package

For a generic Phase 0 package:

```bash
uv run nlreq package path/to/requirement.nlreq \
  --out requirements/REQ-EXAMPLE-001 \
  --requirement-id REQ-EXAMPLE-001 \
  --title "Short requirement title" \
  --claim-kind state_precondition
```

For a Python adapter package:

```bash
uv run nlreq python-package path/to/requirement.nlreq \
  --out requirements/REQ-PY-001 \
  --requirement-id REQ-PY-001 \
  --title "Python operation succeeds for approved actor" \
  --claim-kind state_precondition \
  --package-root tests/fixtures/adapters/pythonpkg/samplepkg \
  --package-name samplepkg \
  --project-root . \
  --test-path tests/fixtures/adapters/pythonpkg
```

## 3. Review The Package

Render a checklist:

```bash
uv run nlreq review-template REQ-EXAMPLE-001
```

Review the controlled form, source spans, assumptions, bindings, evidence level,
and unsupported claims before accepting the package.

## 4. Validate

Generic package:

```bash
uv run nlreq validate requirements/REQ-EXAMPLE-001
```

Python package:

```bash
uv run nlreq python-validate requirements/REQ-PY-001 \
  --package-root tests/fixtures/adapters/pythonpkg/samplepkg \
  --package-name samplepkg \
  --project-root . \
  --test-path tests/fixtures/adapters/pythonpkg
```

## 5. Refresh Adoption Artifacts

```bash
uv run nlreq package-index requirements --out requirements/index.json
uv run nlreq ci-report requirements --out /tmp/nlreq-ci-report.json
```

In shadow mode, CI reports findings without blocking the build.

## 6. Reference The Requirement In An Implementation PR

Implementation PRs should include the requirement id in the PR body or commit
message:

```text
Requirement: REQ-EXAMPLE-001
```

Run the soft gate in report-only mode:

```bash
uv run nlreq soft-gate requirements --references-file /tmp/pr-body.md
```

After the workflow is stable, CI can opt into non-zero failures for blockers:

```bash
uv run nlreq soft-gate requirements --references-file /tmp/pr-body.md --fail-on-blocking
```
