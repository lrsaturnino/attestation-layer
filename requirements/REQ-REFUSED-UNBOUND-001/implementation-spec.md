# REQ-REFUSED-UNBOUND-001

## Requirement

Unbound operator example

## Controlled Form

```text
For every operation request:
if operator is not authorized
then operation must be rejected before state_change.
```

## Scope

- Adapter: generic
- `operation` -> `generic:operation` (action)
- `state_change` -> `generic:state_change` (state_transition)

## Required Behavior

Action `operation` must satisfy `rejected_before` under the declared conditions.

## Evidence

- IR type-checked.
- Symbols resolved through generic adapter.
- Self-consistency checked.
- Supported claim shape SMT-checked.

## Status

`REFUSED_UNBOUND_SYMBOLS`
