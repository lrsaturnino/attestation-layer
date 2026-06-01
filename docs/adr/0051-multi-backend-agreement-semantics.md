# ADR 0051: Multi-Backend Agreement Semantics

## Status

Proposed

## Context

The proof object can contain evidence from multiple formal backends, but multiple
results only increase confidence when their semantics overlap and their outputs
do not contradict each other. Without an explicit agreement artifact, a proof
could include one valid result and one counterexample-producing result without
making that conflict visible to closure.

## Decision

Introduce a backend agreement report.

Every comparable backend result must declare an `overlap_key`. Pairwise
comparison only occurs when both sides have the same key. Otherwise the pair is
recorded as `non_overlap`.

For overlapping pairs, agreement requires equality of:

- result status;
- evidence level;
- verification bounds;
- unsupported constructs;
- counterexamples, when either side reports them.

The report has a policy:

- `blocking` turns disagreement or complete non-overlap into closure effect
  `block`;
- `report_only` records the same finding with closure effect `report_only`.

Proof closure may include the report. If the included report has closure effect
`block`, its blockers become proof blockers.

## Consequences

Backend diversity is no longer a count of tools. It requires declared semantic
overlap and deterministic output comparison.

Non-overlap remains useful context, but it cannot masquerade as agreement.
Future work can refine `overlap_key` into a richer formal semantic profile with
per-construct equivalence claims.
