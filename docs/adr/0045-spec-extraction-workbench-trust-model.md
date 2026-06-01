# ADR 0045: Spec Extraction Workbench Trust Model

## Status

Proposed

## Context

Brownfield modules often lack reviewed formal specs. Blocking forever on missing
spec coverage is correct for proof closure, but it leaves reviewers without a
structured starting point. The roadmap calls for a Specula-like workbench that
can use static structure, code presentation, draft generation, and trace
grounding to propose candidate specs while preserving a strict trust boundary.

## Decision

Introduce a spec extraction workbench report.

The report identifies affected modules without fresh reviewed specs and emits a
candidate spec for each. Every candidate records:

- module id and candidate path;
- formalism;
- draft review status and unknown freshness;
- content and content hash;
- extraction provenance;
- optional code-presentation hash;
- optional trace-replay hash;
- known gaps.

Candidate specs can be converted to draft system spec entries, but those entries
remain `review_status=draft` and `freshness=unknown`. They do not satisfy spec
coverage.

Promotion to a reviewed spec entry is a separate hash-checked operation. The
approved hash must match the extracted content hash, and the resulting reviewed
entry records that hash.

## Consequences

The system can help reviewers bootstrap missing specs without weakening proof
closure. Draft extraction output is useful context, but never trusted evidence.

Future phases can improve extraction quality with richer static analysis, LLM
drafting, and trace grounding while preserving the same review/promotion
contract.
