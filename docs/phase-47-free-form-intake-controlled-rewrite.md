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

## Implementation Spec

Input artifacts:

- Original user text from a file or product surface.
- A proposed controlled rewrite, currently supplied explicitly by CLI and
  later usable by an LLM or rule-based producer.
- Optional producer metadata: method, model, prompt, timestamp, and free-form
  metadata.

Output artifacts:

- `FreeFormIntakeArtifact` records the original text and its hash.
- `ControlledRewriteProposal` records the proposed controlled text, text hash,
  unified diff, diff hash, and producer metadata.
- `ControlledRewriteApproval` records the reviewer, decision, original-text
  hash, controlled-text hash, and diff hash.

Required lifecycle:

1. Capture original text with `nlreq intake-draft`.
2. Create a proposal that names the exact controlled text under review.
3. Review the diff outside the parser trust boundary.
4. Call `controlled_text_for_parsing` only with a matching approved artifact.

Validation behavior:

- Raw free-form text is never returned by parser-facing helpers.
- The approval must reference the same proposal ID.
- The approval must match the original intake hash, controlled text hash, and
  diff hash.
- A rejected or absent approval raises a refusal before parsing.

Failure modes:

- Missing approval: `NLR-INTAKE-UNAPPROVED` at the product layer.
- Original hash mismatch: stale or tampered intake approval.
- Controlled text or diff mismatch: stale or tampered rewrite approval.

Tests:

- `tests/test_milestone_group1.py` proves unapproved proposals cannot be parsed,
  approvals are hash-bound, and original-hash tampering is rejected.

Out of scope:

- This phase does not trust an LLM rewrite. It records LLM metadata only so a
  reviewer can audit the suggestion before controlled parsing.
