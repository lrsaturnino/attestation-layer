# Phase 118 Rewrite Provenance And Replay

Phase 118 makes controlled rewrite evidence replayable enough for audit.

## Purpose

LLM and manual rewrite processes may be non-deterministic. Replay evidence must
therefore retain exact outputs, prompt metadata, provider metadata, hashes, and
approval bindings rather than assuming the provider can reproduce the same text.

## Contracts

`src/nlreq/intake.py` defines:

- `RewritePromptRegistryEntry`
- `RewritePromptRegistry`
- `RewriteReplayAttempt`
- `RewriteApprovalReplayRecord`
- `RewriteReplayBundle`
- `build_prompt_registry_entry`
- `build_rewrite_replay_bundle`

## Replay Bundle Semantics

A replay bundle includes:

- the original `FreeFormIntakeArtifact`;
- each retained rewrite attempt;
- proposal output text and output hash;
- diff and diff hash;
- producer method, model, prompt hash, tool version, and metadata;
- approval decision records;
- optional prompt registry;
- selected proposal ID and selected controlled text hash;
- replay hashes over intake, attempts, approvals, and prompt registry.

## Non-Determinism Policy

Replay does not require an LLM to produce byte-identical output. It requires the
original output and enough metadata to explain how that output was produced and
why a reviewer approved or rejected it.

## Approval Invalidation

Any rewrite text or diff change changes its hash. Existing approvals no longer
match and `controlled_text_for_parsing` refuses the proposal.

## Exit Criteria

This phase exits when:

- replay bundles retain original text, rewrite output, diff, prompts, producer
  metadata, and approval bindings;
- selected proposal hashes are recorded;
- any rewrite mutation invalidates approval;
- tests prove replay hashes and selected hashes are present.
