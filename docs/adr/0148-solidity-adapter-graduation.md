# ADR 0148: Solidity Adapter Graduation

## Status

Accepted

## Context

Solidity is the project's transaction/event ecosystem pressure test. Earlier
work added a static Solidity adapter, but milestone group 13 needs that adapter
to participate in v2 capability certification and to keep EVM-specific facts
outside requirement IR.

## Decision

Graduate `SoliditySourceAdapter` under the v2 adapter contract.

The adapter declares `ecosystem=transaction_event`, supports contracts,
libraries, interfaces, functions, events, and modifiers, and consumes normalized
transaction traces from Foundry or debug-trace-style producers. Event role
metadata remains in source-symbol artifacts. Overloaded functions with the same
source name are ambiguous and block certification unless a later binding
strategy supplies unique signatures.

Inheritance, virtual dispatch, and modifier expansion remain declared
limitations of this static slice.

## Consequences

Solidity can certify as a production candidate when a manifest supplies
resolvable symbols and normalized traces. Overload ambiguity is now preserved
instead of hidden by last-write-wins symbol extraction.

The tradeoff is that deeper Solidity analysis still requires adapter-local
tooling such as Slither-class project analysis before those facts become
gateable.

## Validation

Group 13 tests verify overload blocking, event role metadata, normalized EVM
trace consumption, and production-candidate certification.
