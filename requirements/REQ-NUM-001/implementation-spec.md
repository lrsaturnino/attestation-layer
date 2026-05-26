# REQ-NUM-001

## Requirement

Counter increments within limit

## Controlled Form

```text
For every operation request:
if counter is at most limit
then operation must increase counter by 1.
```

## Scope

- Adapter: generic
- `counter` -> `generic:counter` (quantity)
- `limit` -> `generic:limit` (quantity)
- `operation` -> `generic:operation` (action)

## Required Behavior

Action `operation` must satisfy `increase` under the declared conditions.

## Evidence

- IR type-checked.
- Symbols resolved through generic adapter.
- Self-consistency checked.
- Supported claim shape SMT-checked.

## Status

`ACCEPTED_WITH_EVIDENCE`
