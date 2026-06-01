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
- `TranslatorCandidateV2`
- `TranslatorSelectionArtifact`

CLI:

```bash
uv run nlreq translate-candidates requirement.nlreq3 --run-id RUN-1 \
  --requirement-id REQ-1 --title "Requirement" --out run.json
uv run nlreq translate-compare run.json --out comparison.json
uv run nlreq translate-select run.json --candidate-id candidate-dsl-v3 \
  --approved-by reviewer@example.invalid --out selection.json
```

## Invariants

- Candidate generation records source text hash and replay metadata.
- Candidate comparison feeds the existing translation agreement report.
- LLM candidates cannot be selected unless explicitly approved.

## Exit Criteria

Translator runs are reproducible enough to audit, and candidate selection is
review-bound.
