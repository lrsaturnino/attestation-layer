# ADR 0038: Agnosticism And Cross-Language Proof Model

## Status

Proposed

## Context

The roadmap requires proof that the Attestation Layer is infrastructure rather
than a single-language or single-formalism implementation. By Phase 29 the IR,
source adapter boundary, formal backend boundary, and proof closure gate exist.
The remaining step is a deterministic artifact that records when a closed proof
has crossed one abstraction boundary.

## Decision

Introduce an agnostic wedge report.

The report consumes a closed proof object plus optional source manifests, formal
backend responses, and the compositional IR. It passes when either:

- at least two distinct source languages are present; or
- at least two distinct formal targets are present.

The report also checks that formal backend responses are represented in the
proof object and that semantic IR metadata does not contain adapter-specific
facts such as language, runtime, adapter id, source path, backend, or target.

The report lists limitations for any axis not demonstrated.

## Consequences

Version 0.1 can prove agnosticism at the boundary level without claiming full
semantic equivalence across languages or formalisms. Future phases can strengthen
the report with cross-language trace causality and multi-backend agreement
rules while preserving the IR spine.
