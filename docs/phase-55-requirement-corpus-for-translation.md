# Phase 55 Requirement Corpus For Translation

Phase 55 measures translation quality independently from backend verification.

## Corpus

The seed corpus lives at `benchmarks/requirements-translation/corpus.json`.
It includes:

- clean controlled text;
- ambiguous prose requiring clarification;
- adversarial prose requiring refusal.

Future beta work should grow the corpus to at least 100 cases before using it
as a release-quality public benchmark.

## Contracts

`src/nlreq/translation_benchmark.py` defines:

- `RequirementTranslationCorpus`
- `RequirementTranslationResults`
- `RequirementTranslationBenchmarkReport`

CLI:

```bash
uv run nlreq benchmark-translation \
  --corpus benchmarks/requirements-translation/corpus.json \
  --results benchmarks/requirements-translation/observed-results.example.json
```

## Metrics

- syntactic validity rate;
- semantic match rate;
- clarification quality;
- refusal correctness;
- runtime total.

## Exit Criteria

Translator changes can be evaluated without formal backend execution.

## Implementation Spec

Input artifacts:

- `RequirementTranslationCorpus` with unique case IDs and expected outcomes.
- `RequirementTranslationResults` with observed outcomes, syntax validity,
  semantic-match flags, clarification questions, refusal codes, and runtime.

Output artifacts:

- `RequirementTranslationBenchmarkReport` with aggregate rates and per-case
  observations.

Case contract:

- `expected_ir_path` must be corpus-root-relative and cannot traverse upward.
- Accepted cases require semantic match.
- Clarification cases require expected questions to be a subset of observed
  questions after normalization.
- Refusal cases require the expected refusal code.

Metrics:

- Syntactic validity rate.
- Semantic match rate.
- Clarification quality.
- Refusal correctness.
- Runtime total across supplied observations.

Failure modes:

- Missing observations produce `missing`.
- Outcome mismatch, semantic mismatch, clarification mismatch, and refusal
  mismatch are distinct statuses.

Tests:

- `tests/test_milestone_group1.py` verifies accepted, clarification, and
  refusal scoring in one seed report.

Out of scope:

- The seed corpus is not beta-sized. It defines the methodology and fixtures;
  later roadmap work must expand it before public release claims.
