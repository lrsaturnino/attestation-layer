# ADR 0032: Spec Coverage And Specula Boundary

## Status

Proposed

## Context

Impact analysis can identify affected modules, and the system spec registry can
identify reviewed specs. The project needs a coverage artifact connecting those
two views before `S ∧ R` results can be trusted in brownfield systems.

## Decision

Introduce spec coverage reports over affected modules.

A module is covered only when it has a fresh reviewed spec registry entry.
Missing, stale, or unreviewed specs are blocking states.

Specula-style extraction is explicitly outside the trust boundary in this phase.
Extraction may propose draft specs later, but extracted output is not coverage
until reviewed and registered.

## Consequences

The project can block requirements touching under-specified modules without
pretending extraction exists.
