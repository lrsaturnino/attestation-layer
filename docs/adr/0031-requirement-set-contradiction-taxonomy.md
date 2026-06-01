# ADR 0031: Requirement-Set Contradiction Taxonomy

## Status

Proposed

## Context

The current self-consistency check detects contradictions inside one flat claim.
The roadmap requires detecting contradictions across a requirement set.

The full ALICE-style taxonomy is broader than the first implementation should
attempt. Phase 26 needs a stable artifact shape and one deterministic taxonomy
slice.

## Decision

Introduce a requirement-set consistency report.

The first taxonomy category is `opposite_predicate`: two requirements in the
same checked set assert direct opposite predicates over the same arguments, such
as `approved(actor)` and `not_approved(actor)`.

The report records:

- contradiction type;
- participating requirement ids;
- predicate fragments;
- source spans where available.

Future phases may extend the taxonomy without changing the rule that
contradictions are non-approving.

## Consequences

The project gains cross-requirement consistency artifacts while keeping the
first rule deterministic and easy to audit.

The tradeoff is limited semantic coverage. Many real contradictions will remain
unsupported until the taxonomy expands.
