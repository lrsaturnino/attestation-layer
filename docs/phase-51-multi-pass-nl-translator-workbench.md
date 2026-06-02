# Phase 51 Multi-Pass NL Translator Workbench

Phase 51 introduces an auditable translator workbench. LLM outputs are candidate
artifacts, not trusted formal artifacts.

## Strategies

- Deterministic DSL v3 parser.
- LLM semantic decomposition candidates.
- Rule-based post-processor candidates.
- Optional second-model audit candidates.

## Contracts

`src/nlreq/translator_workbench.py` defines:

- `TranslatorRunArtifact`
- `TranslatorCandidateArtifact`
- `TranslatorSelectionArtifact`

CLI:

```bash
uv run nlreq translate-candidates requirement.nlreq3 --run-id RUN-1 \
  --requirement-id REQ-1 --title "Requirement" --out run.json
uv run nlreq translate-compare run.json --out comparison.json
uv run nlreq translate-select run.json --candidate-id candidate-dsl-v3-parser \
  --approved-by reviewer@example.invalid --out selection.json
```

## Invariants

- Candidate generation records source text hash and replay metadata.
- Candidate comparison validates source text hashes and feeds the existing
  translation agreement report.
- LLM candidates cannot be selected unless explicitly approved.

## Exit Criteria

Translator runs are reproducible enough to audit, and candidate selection is
review-bound.

## Implementation Spec

Input artifacts:

- Approved controlled DSL v3 text.
- Run metadata: run ID, requirement ID, and title.
- Future candidate producers may add LLM, rule-based, or audit candidates to
  the same run shape.

Output artifacts:

- `TranslatorRunArtifact` records source text hash, candidates, and optional
  selected candidate ID.
- `TranslatorCandidateArtifact` records strategy, method, requirement IR, source text
  hash, replay metadata, and optional approval.
- `TranslatorSelectionArtifact` records selected candidate hash and selection
  approval.

Default candidate generation:

- The CLI emits a deterministic DSL v3 parser candidate and a deterministic
  rule-based post-processor candidate over canonical controlled text.
- Both candidates carry the same source text hash and separate replay metadata.
- Single-candidate runs remain supported for narrow tests and diagnostics, but
  the product command produces a comparison-ready run by default.

Comparison behavior:

- `compare_translator_run` converts workbench candidates into the existing
  `TranslationAgreementInput` shape.
- Candidate source hashes must match the run source hash or comparison fails.
- Runs with only one candidate produce `needs_review` through the structural
  agreement layer.
- Later logical agreement can consume selected or compared candidates without
  changing the workbench storage contract.

Selection behavior:

- Candidate source hashes must match the run source hash or selection fails.
- Deterministic and manual candidates may be selected with an explicit reviewer
  approval.
- LLM candidates require a candidate-level approval before selection.
- Selection records the hash of the exact IR candidate selected.

Tests:

- `tests/test_milestone_group1.py` verifies single-candidate review blocking
  approved candidate selection, and CLI multi-pass candidate generation.

Out of scope:

- This phase does not call external LLM APIs. It defines the untrusted candidate
  protocol and deterministic replay path.
