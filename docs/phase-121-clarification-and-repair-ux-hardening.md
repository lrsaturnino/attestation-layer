# Phase 121 Clarification And Repair UX Hardening

Phase 121 makes translation repair auditable and versioned.

## Purpose

Clarification should help users repair requirements, but it must not silently
rewrite the selected controlled form. A repair response creates a new proposed
controlled-form version that needs explicit approval before downstream artifacts
can bind to it.

## Contracts

`src/nlreq/translation_repair.py` defines:

- `ControlledFormVersion`
- `TranslationRepairResponse`
- `TranslationRepairHistory`
- `create_controlled_form_version`
- `build_translation_repair_history`
- `apply_translation_repair_response`
- `approve_controlled_form_history_version`
- `selected_controlled_form_text`

## Prompt Semantics

Repair prompts retain:

- prompt ID;
- question;
- target stage;
- source spans when available;
- no-span reason when unavailable;
- next actions.

## Version Semantics

Controlled form versions have statuses:

- `drafted`
- `proposed`
- `approved`
- `rejected`
- `superseded`

Repair responses create `proposed` versions. Approving a proposed version sets
it as selected and supersedes any previously approved version.

## No Silent Rewrite

`selected_controlled_form_text` returns only an approved selected version. If no
approved version exists, it raises an error.

## Exit Criteria

This phase exits when:

- repair responses are tied to prompt IDs;
- repair responses create new proposed versions;
- previous versions remain retained;
- downstream selection requires approval;
- tests cover proposed and approved version transitions.
