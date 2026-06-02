# ADR 0122: Reference Brownfield Demo Contract

## Status

Accepted

## Context

The reference demo report checks artifact presence and expected decisions. The
extended conclusion release needs stronger proof that the demo exercises the
release path and can be replayed.

## Decision

Add `ExtendedReferenceDemoReport`.

The extended demo requires:

- the base demo report to be reproducible;
- extended gate reports for demo requirements;
- replay bundle hashes for every gate report;
- required pipeline stages for accepted requirements;
- expected accepted and refused outcomes.

Expected refused requirements can have failed gate stages when the refusal is
the expected outcome and a replay bundle is present.

## Rationale

A useful reference demo must show success and failure. Treating expected
refusals as invalid would bias demos toward happy paths and weaken release
evidence.

## Consequences

Positive:

- Demo evidence includes replayability.
- Accepted and refused paths are both represented.
- Decision mismatches and missing replay bundles block release readiness.

Negative:

- Demo maintenance requires keeping gate reports and replay bundles current.

## Validation

`tests/test_milestone_group9.py` verifies reproducible extended demos and
missing replay bundle blocking.
