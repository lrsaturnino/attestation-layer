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

## Implementation Spec

Input artifacts:

- `EndToEndRequirementGateReport` with stage-level blockers and decision.
- Source-span-bearing blockers or artifacts from earlier phases when available.

Output artifacts:

- `ProductRefusalReport` with a stable decision and one finding per blocker.
- Markdown rendered by `refusal_report_markdown`.

Classification rules:

- `translation_agreement` maps to `NLR-TRANSLATION-DISAGREEMENT`.
- `requirement_self_consistency` maps to self-contradiction or formal unknown.
- `system_consistency` maps to system inconsistency or formal unknown.
- Coverage, trace, producer, and closure blockers map to stable product codes.
- Unknown statuses remain `unknown`; they are not collapsed into refusal.

Finding contract:

- Every finding includes a code, category, stage, message, likely owner, and
  next action.
- A finding preserves blocker source spans when present.
- A finding without source spans must include a `no_span_reason`.
- Markdown and JSON are generated from the same model to avoid drift.

Failure modes:

- Stage-level blockers without spans remain actionable through owner and next
  action fields.
- Unsupported stages fall back to `NLR-CLOSURE-BLOCKED`.

Tests:

- `tests/test_milestone_group1.py` verifies gate blocker mapping and Markdown
  rendering for a translation disagreement.
- The same module verifies source-span-bearing blockers stay span-grounded in
  the product refusal report.

Out of scope:

- This phase does not replace formal counterexample rendering. Phase 59 owns
  normalized counterexample detail.
