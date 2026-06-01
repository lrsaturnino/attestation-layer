# Phase 48 Controlled Requirement DSL v3

Phase 48 expands the controlled grammar while keeping parsing deterministic.

## Supported Requirement Classes

- `authorization_precondition`
- `state_precondition`
- `state_postcondition`
- `event_state_correspondence`
- `numeric_invariant`
- `bounded_temporal`
- `cross_module_causal_obligation`

## Syntax

```text
requirement <class>:
scope <entity>
when <predicate> [and <predicate>]*
then <obligation> [and <obligation>]*
```

Predicates cover authorization, approval, confirmation, state equality,
membership, and numeric comparisons. Obligations cover success, rejection before
a state transition, post-state assignment, event-within bounds, numeric
invariants, and cross-module causal obligations.

## Contracts

`src/nlreq/dsl_v3.lark` defines the grammar. `src/nlreq/dsl_v3.py` defines the
canonical formatter and parser.

CLI:

```bash
uv run nlreq ir-v3 requirement.nlreq3 --requirement-id REQ-1 --title "Requirement"
```

## Invariants

- Canonical text is byte-stable.
- Every IR node carries deterministic source spans.
- Unsupported constructs fail at parse time with a structured location.
- DSL version is independent from IR version.

## Exit Criteria

Fixtures cover every supported requirement class and validate as IR 0.2.
