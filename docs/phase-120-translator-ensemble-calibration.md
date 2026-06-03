# Phase 120 Translator Ensemble Calibration

Phase 120 makes translator agreement measurable against semantic labels.

## Purpose

Structural equality is not enough to claim semantic agreement. The system must
measure agreement behavior on labeled cases, track false semantic acceptance,
and allow release policy to fail when agreement accepts candidates that are
known to mean different things.

## Contracts

`src/nlreq/semantic_agreement.py` defines:

- `SemanticAgreementCalibrationCase`
- `SemanticAgreementCalibrationObservation`
- `SemanticAgreementCalibrationReport`
- `build_semantic_agreement_calibration_report`

Existing agreement reports still compare formal claim candidates with named
profiles:

- `canonical_formal_claim_equality`
- `alpha_identifier_equivalence`
- `commutative_claim_equivalence`
- `unsupported`

## Calibration Semantics

Each calibration case supplies:

- case ID;
- expected same-meaning label;
- observed `SemanticAgreementReport`.

The calibration report computes:

- matched cases;
- semantic accuracy;
- false acceptance count;
- false refusal count;
- blockers for configured budgets.

## Release Policy

False semantic acceptance budget defaults to zero. Any accepted disagreement
case beyond the budget fails calibration.

## Exit Criteria

This phase exits when:

- agreement reports are measurable against semantic labels;
- false acceptance and false refusal are explicit observations;
- false acceptance budget breaches fail calibration;
- reviewer resolution remains hash-bound in the underlying agreement report.
