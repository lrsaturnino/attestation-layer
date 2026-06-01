# ADR 0050: Real Evidence Producer Registry

## Status

Proposed

## Context

Proof closure already uses a producer mapping to decide which backends may emit
which evidence levels. The roadmap requires stronger anti-forgery checks for
high-assurance evidence: actual producers need tool identity and reproducibility
metadata, not just a trusted label.

## Decision

Introduce an evidence producer validation report.

For high-assurance levels (`BOUNDED_CHECKED` and `PROVEN_INDUCTIVE`), validation
requires:

- registered producer id matching the backend result;
- evidence level allowed by producer policy;
- producer marked as real;
- tool version from producer or result metadata;
- command metadata;
- input/output or artifact hashes.

Low-assurance results are marked not applicable.

## Consequences

High-assurance evidence can no longer be a bare label. Consumers can require a
producer validation report before trusting bounded or proof-level evidence in
closure.

The report validates metadata only. Future work can add binary attestation,
signature checks, and automatic re-runs.
