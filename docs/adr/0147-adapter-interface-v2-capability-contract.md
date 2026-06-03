# ADR 0147: Adapter Interface v2 Capability Contract

## Status

Accepted

## Context

The source adapter interface existed, but adapters could pass certification
without a durable machine-readable statement of what they could and could not
support. That made it too easy for downstream gates to treat static symbol
resolution, trace grounding, source presentation, and coverage mapping as if
they were the same kind of evidence.

## Decision

Introduce `AdapterCapabilityContract` with `interface_version=2.0`.

The contract records adapter identity, ecosystem, required methods, capability
claims, supported evidence labels, supported symbol types, trace runtimes,
limitations, and failure taxonomy. Certification can require specific
capabilities and blocks when the contract is missing required methods or claims.

`supported_evidence` must be backed by capability claims. Unsupported language
features are represented as limitations with explicit closure effects.

## Consequences

Gate policy can now ask for concrete adapter capabilities instead of only an
adapter id. Adapters cannot list an evidence label without a supporting
capability claim. The project also gains a stable schema for comparing adapter
depth across ecosystems.

The tradeoff is that adapter authors must maintain capability metadata as part
of the implementation, not as prose-only documentation.

## Validation

Group 13 tests verify v2 contract fields, required capability blocking, source
presentation checks, and schema generation.
