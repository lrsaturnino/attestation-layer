# Phase 123 Semantic Translation Benchmark Release Bar

Phase 123 adds release-bar semantics to the translation benchmark.

## Purpose

Benchmark reporting must not be just descriptive. Release policy needs explicit
thresholds that fail on false semantic acceptance, insufficient semantic match,
missing expected outcome classes, weak clarification quality, or weak refusal
correctness.

## Contracts

`src/nlreq/translation_benchmark.py` defines:

- `RequirementTranslationReleaseThresholds`
- `RequirementTranslationReleaseBarReport`
- `evaluate_translation_benchmark_release_bar`

Benchmark reports now include:

- false acceptance count and rate;
- false refusal count and rate;
- corpus-scoped observations;
- release-bar evaluation hash.

## Default Release Thresholds

Default thresholds are intentionally strict:

- false acceptance budget: `0`;
- minimum semantic match rate: `1.0`;
- required expected outcomes: accepted, clarification, refused, needs review.

Projects may lower thresholds for exploratory runs, but release certification
should keep false acceptance at zero.

## Corpus-Scoped Scoring

The benchmark report scores only cases present in the corpus. Extra observed
results do not improve rates or runtime numbers.

## Exit Criteria

This phase exits when:

- false acceptance is counted and release-blocking by default;
- false refusal can be tracked with a configured budget;
- required expected outcomes are enforced;
- release-bar reports hash the underlying benchmark report;
- tests cover release failure on false acceptance.
