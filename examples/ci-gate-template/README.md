# CI Gate Template

Use this template when integrating the requirement gate into a CI or PR
workflow.

## Minimal Flow

1. Produce an end-to-end requirement gate report.
2. Render a CI/PR gate report in `report_only`, `soft_gate`, or `hard_gate`
   mode.
3. Publish Markdown only as a rendering of the JSON report.
4. Fail the job only from the machine-readable `blocked` result.

Relevant schemas:

- `schemas/end-to-end-requirement-gate.schema.json`
- `schemas/ci-pr-gate-report.schema.json`
