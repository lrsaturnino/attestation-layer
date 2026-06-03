# ADR 0130: Clarification And Repair UX

## Status

Accepted

## Context

Repair prompts existed, but repair responses did not create a durable
controlled-form version history. The roadmap requires clarification and repair
to be actionable without silently rewriting approved text.

## Decision

Introduce controlled-form versions and repair history. Repair responses create
new proposed versions. A version becomes selected only after explicit approval.
Approving a new version supersedes the previous approved version.

## Invariants

- Repair prompts name source spans or no-span reasons.
- Repair responses reference a prompt ID and source version ID.
- Proposed repair versions are not selected automatically.
- Downstream selected text must come from an approved selected version.
- Previous versions remain retained and auditable.

## Consequences

The repair loop can support UI and API workflows without weakening controlled
input approval semantics.

## Rejected Alternatives

Mutating the current controlled text in place was rejected because it destroys
review history.

Automatically approving repaired text was rejected because clarification is not
equivalent to reviewer approval.

## Validation

`tests/test_milestone_group10.py` verifies proposed repair versions, selected
approved text, approval of a repaired version, and superseding behavior.
