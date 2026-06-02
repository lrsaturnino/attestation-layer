# Phase 88 Semantic Translation Benchmark Expansion

Phase 88 extends the translation benchmark with semantic closure metrics.

## Purpose

The seed translation benchmark measured syntax, semantic match, clarification,
refusal, and runtime. Milestone 5 needs additional signals for ambiguity,
needs-review outcomes, formal-claim output, semantic profile, and false
acceptance.

## Contracts

`src/nlreq/translation_benchmark.py` remains the benchmark module and now
supports:

- outcome `needs_review`;
- per-case `ambiguous`;
- per-case `false_acceptance`;
- per-case `needs_review_reason`;
- per-case `formal_claim_hash`;
- per-case `semantic_profile`;
- aggregate `ambiguity_rate`;
- aggregate `needs_review_rate`;
- aggregate `false_acceptance_rate`.

Schemas updated:

- `schemas/requirement-translation-corpus.schema.json`
- `schemas/requirement-translation-results.schema.json`
- `schemas/requirement-translation-benchmark-report.schema.json`

CLI remains:

```bash
uv run nlreq benchmark-translation \
  --corpus benchmarks/requirements-translation/corpus.json \
  --results benchmarks/requirements-translation/observed-results.example.json
```

## Scoring Rules

Accepted cases still require semantic match.

Clarification cases still require expected questions to be a subset of observed
questions.

Refusal cases still require the expected refusal code.

Needs-review cases require an observed `needs_review_reason`.

Any result flagged as `false_acceptance` fails the report regardless of matched
outcome counts.

## Compatibility

Existing benchmark corpus and observed result files remain valid because new
fields have defaults.

## Exit Criteria

This phase exits when:

- benchmark reports ambiguity, needs-review, and false-acceptance rates;
- false acceptance fails the report;
- existing seed benchmark fixtures remain valid;
- tests cover the new metrics.

## Tests

`tests/test_milestone_group5.py` verifies the new metrics and false-acceptance
failure behavior. Existing group-1 tests continue to validate backward
compatibility.

## Out Of Scope

This phase does not make the seed corpus public-release sized. It extends the
methodology and schema so later milestones can add more cases.

