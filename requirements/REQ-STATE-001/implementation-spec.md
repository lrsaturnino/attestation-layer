# REQ-STATE-001

## Requirement

Approved operation sets accepted status

## Controlled Form

```text
For every operation request:
if actor is approved
then operation must set operation_status to "accepted".
```

## Scope

- Adapter: generic
- `actor` -> `generic:actor` (principal)
- `operation` -> `generic:operation` (action)
- `operation_status` -> `generic:operation_status` (state)

## Required Behavior

Action `operation` must satisfy `set` under the declared conditions.

## Evidence

- IR type-checked.
- Symbols resolved through generic adapter.
- Self-consistency checked.
- Supported claim shape SMT-checked.

## Status

`ACCEPTED_WITH_EVIDENCE`
