# ADR 0151: Rust Or Java Adapter Graduation

## Status

Accepted

## Context

Phase 142 needs a compiled ecosystem pressure test beyond Go. Rust and Java
exercise different failure modes: Rust macro expansion and compiler facts, Java
overloads and virtual dispatch.

## Decision

Use Rust as the primary phase 142 graduation adapter and keep Java as a
companion compiled-service adapter.

`RustSourceAdapter` declares `ecosystem=compiled_system` and supports functions,
structs, enums, and traits. Macro-expanded symbols require deeper external
evidence.

`JavaSourceAdapter` declares `ecosystem=compiled_service` and supports classes,
interfaces, enums, and methods. Overloaded method names are ambiguous unless a
future signature-aware binding strategy is supplied. Inheritance and virtual
dispatch remain review-depth limitations in the static slice.

## Consequences

The adapter interface is pressure-tested against a systems language and a JVM
service language without changing requirement IR. Java overload ambiguity is
blocking, which prevents false static closure.

The tradeoff is that both adapters remain lexical until rust-analyzer, JDT, or
bytecode-level tooling is integrated adapter-locally.

## Validation

Group 13 tests verify Rust static certification and Java overload blocking.
