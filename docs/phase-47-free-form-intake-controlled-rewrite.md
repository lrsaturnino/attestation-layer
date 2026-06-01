# Phase 47 Free-Form Intake And Controlled Rewrite

Phase 47 adds a safe product path from human prose to controlled requirements.
Raw free-form text remains untrusted.

## Scope

- Capture the original free-form text and hash.
- Propose controlled text with method, model, prompt hash, timestamp, and diff.
- Require explicit approval before parsing proposed controlled text.
- Bind approval to both the controlled text hash and diff hash.

## Contracts

`src/nlreq/intake.py` defines:

- `FreeFormIntakeArtifact`
- `ControlledRewriteProposal`
- `ControlledRewriteApproval`

CLI commands:

```bash
uv run nlreq intake-draft original.txt --suggested requirement.nlreq3 \
  --intake-id INTAKE-1 --proposal-id PROP-1 --out proposal.json
uv run nlreq intake-approve proposal.json --approval-id APP-1 \
  --approved-by reviewer@example.invalid --out approval.json
uv run nlreq intake-diff proposal.json
```

## Invariants

- Parser entry points must use approved controlled text, not raw prose.
- Approval becomes invalid when controlled text or diff hashes change.
- LLM rewrites are untrusted suggestions until review.

## Exit Criteria

Tests prove unapproved rewrite proposals cannot be parsed and the diff hash is
bound into the approval.
