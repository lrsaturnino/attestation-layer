# Phase 115 Threat Model And TCB Review

Phase 115 converts the threat model into release certification evidence.

## Purpose

The conclusion claim depends on trusted components: parsers, validators,
translators, backends, adapters, trace producers, artifact stores, producer
registries, CI gates, and human review. The release must name those components,
their assumptions, evidence attack scenarios, release artifact hashes, and
accepted residual risks.

## Contracts

Implementation:

- `ExtendedTcbReviewReport`
- `build_extended_tcb_review_report`
- CLI command `nlreq tcb-review`

Schema:

- `schemas/extended-tcb-review-report.schema.json`

## Required Release Artifacts

The default required release artifact hashes are:

- `extended_gate`
- `ci_gate`
- `benchmark`
- `reference_demo`
- `public_docs`
- `certification_bundle`

The report also derives adversarial assumptions from TCB components and names
evidence attack scenarios for forged evidence, tampering, replay, and malicious
adapter risks.

## Decision Rules

The extended TCB review is complete only when:

- the base threat model has no release findings;
- all required release artifact hashes are present;
- every residual risk from the threat model is explicitly accepted.

## Exit Criteria

- Missing release artifact hashes block the review.
- Unaccepted residual risks block the review.
- Evidence attack scenarios are represented in release output.
