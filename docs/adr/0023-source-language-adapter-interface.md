# ADR 0023: Source LanguageAdapter Interface

## Status

Proposed

## Context

The existing `Adapter` interface is oriented around declaration-level artifacts:
OpenAPI documents, GraphQL schemas, JSON Schemas, AsyncAPI documents, Protobuf
files, reviewed TLA+ configs, command checks, and a narrow Python package
adapter. That interface resolves symbols and generates verification tasks, but
it does not define call graphs, code-to-spec manifests, code presentation for
drafting, or trace extraction from source runtimes.

The roadmap needs a source-code boundary before impact analysis and the first
real source vertical. GAP-C1 requires a language-independent `LanguageAdapter`
shape so the core does not become Solidity-, Go-, or Python-specific.

## Decision

Introduce a separate source adapter family.

The first source adapter contract exposes:

- `resolve_symbol`;
- `call_graph`;
- `validate_binding`;
- `present_to_llm`;
- `extract_traces`;
- `parse_manifest`.

The source adapter owns language-specific tooling, source paths, call graph
construction, source symbol binding, code presentation, trace extraction, and
manifest interpretation.

The core owns the shared artifact models, deterministic validation, trace
schema, status semantics, package hashing, and future dispatch decisions.

Declaration adapters and source adapters coexist. A declaration adapter can say
"this reviewed schema declares this contract." A source adapter can say "this
source module contains this symbol, calls this other symbol, and emitted these
normalized traces." Later phases decide how those statements combine.

Phase 21 includes a null source adapter to exercise the contract without
claiming implementation evidence for any real language.

## Consequences

The project gains a stable code-analysis boundary without choosing the first
real source language prematurely. Phase 24 can pick one source vertical and wrap
real tooling behind this interface.

The tradeoff is having two adapter families. That is intentional: declaration
contracts and implementation source code have different responsibilities and
different evidence semantics.
