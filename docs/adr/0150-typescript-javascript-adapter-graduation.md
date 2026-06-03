# ADR 0150: TypeScript And JavaScript Adapter Graduation

## Status

Accepted

## Context

Frontend and service requirements often touch TypeScript and JavaScript. The
adapter boundary must support those ecosystems without pretending dynamic
runtime behavior is statically known.

## Decision

Graduate TypeScript and JavaScript through separate v2 adapter contracts.

`TypeScriptSourceAdapter` declares `ecosystem=frontend_service` and supports
functions, exported values, classes, interfaces, and type declarations.
`JavaScriptProductionSourceAdapter` declares `ecosystem=dynamic_scripting` and
supports functions, exported values, and classes.

Dynamic imports, computed exports, monkey patching, `eval`, and source-map
reconstruction require explicit external evidence or remain unsupported.
Browser and Node traces are consumed only through normalized trace producers.

## Consequences

The system can certify static TypeScript and JavaScript fixtures through the
same adapter contract while honestly refusing dynamic patterns that cannot be
resolved by the static slice.

The tradeoff is that dynamic JavaScript cannot silently close requirements on
static evidence alone.

## Validation

Group 13 tests verify TypeScript static certification, JavaScript production
routing, and explicit unsupported dynamic-pattern limitations.
