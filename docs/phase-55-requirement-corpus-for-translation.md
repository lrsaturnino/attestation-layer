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
