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

## Implementation Spec

Input language:

- DSL v3 documents are line-oriented controlled text with a required
  `requirement <class>:` header, one `scope`, one `when` block, and one `then`
  block.
- Predicates and obligations may be joined with `and`.
- Whitespace is insignificant before canonicalization.

Canonicalization:

- Empty lines are removed.
- Repeated internal whitespace is collapsed to a single space.
- The canonical form always ends with one trailing newline.
- Source spans are computed over canonical text, not raw input text, so golden
  fixtures remain byte-stable.

IR lowering:

- DSL v3 lowers to `RequirementIRV2` with `ir_version` `0.2`.
- The requirement class and DSL version are stored in root metadata.
- Every semantic node is deterministic, carries source-span provenance, and
  identifies `nlreq.dsl_v3` as the derivation tool.

Unsupported behavior:

- Ambiguous or unsupported syntax raises `DslV3ParseError`.
- Parse errors carry line and column when the Lark parser can supply them.
- Unsupported constructs are not lowered to placeholder IR nodes.

Tests:

- `tests/test_milestone_group1.py` covers every supported requirement class and
  verifies source-span stability against canonical text.

Out of scope:

- DSL v3 does not replace DSL v2 or migrate stored requirement packages. It is
  the controlled input grammar for conclusion-roadmap intake.
