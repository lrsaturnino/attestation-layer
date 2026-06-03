# ADR 0127: Rewrite Provenance And Replay

## Status

Accepted

## Context

LLM-assisted rewrites can be non-deterministic. A reviewer still needs to audit
what text was produced, what prompt and metadata were used, what diff was
reviewed, and which exact output was approved.

## Decision

Represent rewrite replay as a retained bundle containing original intake,
rewrite attempts, producer metadata, optional prompt registry, approval records,
selected proposal ID, selected controlled text hash, and replay hashes.

## Invariants

- Replay retains exact proposed controlled text.
- Prompt text is retained when available and hash-linked.
- Provider/model metadata is retained as producer metadata.
- Approval records bind original text hash, controlled text hash, and diff hash.
- Replay explains non-deterministic outputs; it does not require byte-identical
  LLM reproduction.

## Consequences

Audit can verify the selected rewrite and approval even if the original provider
is unavailable or non-deterministic.

## Rejected Alternatives

Storing only prompt hashes was rejected because reviewers need the prompt text
or an equivalent registry entry.

Relying on provider replay was rejected because many providers cannot guarantee
identical output across time.

## Validation

`tests/test_milestone_group10.py` verifies prompt registry hashes, replay hashes,
approval replay records, and selected controlled text hashes.
