# Phase 24 First Real Source Vertical

Phase 24 proves the source adapter boundary with one real language vertical.

The first vertical is Python. This choice is pragmatic: the repository already
ships Python fixtures and package tooling, and Python AST parsing is available
without adding external dependencies.

## Purpose

The phase lets the Attestation Layer say:

```text
A real source adapter can parse source files, resolve implementation symbols,
produce a call graph, present code snippets, extract normalized trace artifacts,
and compute deterministic affected modules from requirement symbols.
```

It does not say:

```text
Python is the final target language.
Solidity or Go support exists.
Semantic LLM impact estimation is authoritative.
The implementation satisfies the requirement.
```

## Why Python First

Python is selected for the first source vertical because:

- it requires no new runtime dependency;
- AST parsing is deterministic in the standard library;
- existing repo tests already exercise Python package fixtures;
- and it proves the source adapter interface before adding heavier Solidity or
  Go tooling.

## Implementation Scope

Phase 24 implementation should include:

- `PythonSourceLanguageAdapter`;
- Python AST symbol resolution for functions/classes;
- deterministic call graph extraction;
- code snippet presentation for resolved symbols;
- normalized trace extraction from manifest-declared trace artifacts;
- deterministic impact analysis from symbols to affected modules;
- JSON schema for impact reports;
- tests against a real Python fixture module.

## Evidence Semantics

The Python source vertical provides source-analysis artifacts. It does not prove
runtime correctness or satisfy high-assurance evidence by itself.

Impact analysis is deterministic and non-approving. Semantic/LLM impact
estimation remains out of scope and, when introduced later, can only be
disagreement-checking.

## Success Criterion

Phase 24 succeeds when:

- one real source adapter resolves symbols from a real code fixture;
- call graph extraction works;
- manifest parsing works;
- deterministic impact analysis returns affected modules;
- normalized traces can be emitted from manifest trace sources;
- and existing declaration adapters remain compatible.

## Boundary

This phase is not Solidity, Go, Specula integration, system-spec registry,
`S ∧ R`, trace alignment, proof closure, or evidence inflation.
