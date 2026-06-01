# Phase 50 Product Refusal Surface v2

Phase 50 makes refusal actionable and stable for product workflows.

## Scope

- Stable refusal codes.
- Refused versus unknown categories.
- Stage, owner, next action, and source-span fields.
- JSON and Markdown renderers.
- Requirement-gate Markdown output.

## Contracts

`src/nlreq/refusal.py` defines `ProductRefusalReport` and
`ProductRefusalFinding`.

CLI:

```bash
uv run nlreq refusal-render gate-report.json --out refusal.json --markdown-out refusal.md
uv run nlreq requirement-gate ... --markdown-out gate.md
```

## Codes

Codes include parser, intake, translation, self-consistency, formal unknown,
system consistency, spec coverage, trace, evidence producer, and closure
blockers.

## Invariants

- Every blocker has a stable code.
- A finding either has source spans or explains why spans are unavailable.
- Markdown and JSON are rendered from the same report object.

## Exit Criteria

Gate blockers map to actionable refusal findings.
