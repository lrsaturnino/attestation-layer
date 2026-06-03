# Phase 117 Production Free-Form Intake Runtime

Phase 117 turns free-form intake from static artifacts into an auditable runtime
state machine.

## Purpose

Raw natural language is useful as evidence of human intent, but it is not a
safe formal input. The runtime records free-form text, proposed controlled
rewrites, review decisions, and the exact approved controlled text hash that may
continue into semantic translation.

## Contracts

`src/nlreq/intake.py` defines:

- `FreeFormIntakeRuntimeRecord`
- `IntakeStateTransition`
- `create_intake_runtime_record`
- `record_rewrite_proposal`
- `record_rewrite_decision`
- `supersede_intake_runtime_record`
- `controlled_text_for_runtime_parsing`

Runtime states are:

- `drafted`
- `proposed`
- `approved`
- `rejected`
- `superseded`

## State Semantics

`drafted` means the original free-form text is retained but no controlled form
has been proposed.

`proposed` means at least one controlled rewrite proposal is attached to the
intake.

`approved` means one proposal has a matching approval and its controlled text
hash is selected.

`rejected` means the reviewed proposal was rejected and cannot be selected for
parsing.

`superseded` means the intake record was replaced by a newer intake path and
cannot transition further.

## Parsing Gate

`controlled_text_for_runtime_parsing` checks:

- runtime state is `approved`;
- proposal is the selected proposal;
- selected controlled text hash matches the proposal;
- approval references the same proposal;
- approval reviewed the same original text hash;
- approval binds the exact controlled text hash and diff hash;
- rejected proposals are refused.

## Evidence

Every transition records:

- previous state;
- next state;
- actor;
- timestamp;
- reason;
- relevant artifact hashes.

## Exit Criteria

This phase exits when:

- raw free-form text can be retained without entering formal parsing;
- approved controlled text selection is hash-bound;
- rejected proposals cannot be selected;
- superseded intakes cannot continue;
- tests cover accepted and rejected runtime paths.
