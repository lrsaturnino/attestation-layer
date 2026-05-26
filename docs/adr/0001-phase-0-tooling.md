# ADR 0001: Phase 0 Tooling

## Status

Accepted

## Context

Phase 0 needs a small, deterministic implementation stack for controlled-language parsing, IR validation, SMT-backed checks, golden tests, and a CLI. The stack should favor auditability and fast iteration over broad framework coverage.

## Decision

Phase 0 uses:

- Python for implementation.
- Lark for controlled-language parsing.
- Pydantic for runtime models and JSON Schema generation.
- Z3 for SMT checks.
- Canonical JSON for package artifacts and hashing.
- pytest for golden-file tests.
- uv for dependency and environment management.
- argparse for the initial CLI.

## Consequences

The first implementation optimizes for local velocity and reproducibility. Developers should use `uv sync --extra dev` and `uv run pytest` rather than invoking `pip` directly. ANTLR, CVC5, TypeScript/Zod, and model-checking tools can be evaluated later through separate ADRs.
