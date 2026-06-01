# Phase 42 Backend Agreement

Phase 42 adds a deterministic agreement artifact for comparing formal backend
results that claim to cover the same semantic fragment.

## Purpose

The phase lets the Attestation Layer say:

```text
These backend results overlap, agree on status, agree on bounds, and do not hide
different unsupported constructs or counterexamples.
```

It does not say:

```text
Different formalisms always have identical semantics.
Non-overlapping results strengthen each other automatically.
Report-only disagreement can close a proof.
```

## Implementation Scope

Phase 42 implementation includes:

- backend agreement report model and schema;
- pairwise comparison of overlapping backend results;
- status, evidence level, bound, unsupported-construct, and counterexample
  comparison;
- explicit non-overlap recording when results do not declare a shared
  `overlap_key`;
- blocking versus report-only policy;
- CLI command for `backend-agreement`;
- optional proof object integration so supplied blocking disagreement becomes a
  closure blocker;
- tests for agreement, disagreement, counterexamples, non-overlap, CLI output,
  and proof-closure blocking.

## Agreement Semantics

Backend results must declare the same `overlap_key` before they are compared.
When keys differ or are absent, the report records `non_overlap` rather than
guessing semantic equivalence.

An overlapping pair disagrees if any compared field differs:

- backend status;
- evidence level;
- verification bounds;
- unsupported constructs;
- counterexamples, when present.

The report carries a `closure_effect`:

- `allow` when no blocking issue exists;
- `block` when blocking policy finds disagreement or no overlap;
- `report_only` when policy records the issue without blocking closure.

## Success Criterion

Phase 42 succeeds when:

- agreement and disagreement are reproducible artifacts;
- non-overlap is visible instead of silently treated as confidence;
- proof closure can consume a backend agreement report and block downstream
  action on disagreement.

## Boundary

This phase compares normalized backend result artifacts. It does not prove that
two formalisms are semantically equivalent, and it does not execute the backend
tools itself.
