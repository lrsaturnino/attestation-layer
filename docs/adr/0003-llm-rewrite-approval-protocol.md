# ADR 0003: LLM Rewrite Approval Protocol

## Status

Accepted

## Context

LLMs may help convert free-form requirements into controlled language, but that rewrite can change semantics. If the rewrite silently becomes the requirement, downstream deterministic checks may verify the wrong thing.

## Decision

An LLM-generated controlled form cannot enter parsing or verification until explicitly approved.

Packages that use an LLM rewrite must preserve:

- original free-form text,
- LLM-suggested controlled form,
- approved controlled form,
- diff between original and controlled form,
- model/provider metadata,
- prompt/template version,
- timestamp,
- and approval record.

The approval surface must show the original and controlled forms side by side.

## Consequences

LLMs remain drafting tools, not authorities. The audit trail records where semantic interpretation entered the process.
