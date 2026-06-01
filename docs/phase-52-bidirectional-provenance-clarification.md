# Phase 52 Bidirectional Provenance And Clarification

Phase 52 makes formal fragments explainable back to requirement text and
supports targeted clarification.

## Scope

- Text-span to IR-node provenance.
- IR-node to lowered formal artifact provenance.
- Refusal diagnostics attached to IR nodes.
- Clarification requests from translation disagreement.
- Clarification responses that create new controlled text versions.

## Contracts

`src/nlreq/provenance.py` defines:

- `ProvenanceGraph`
- `ClarificationRequest`
- `ClarificationResponse`
- `ClarifiedControlledText`

CLI:

```bash
uv run nlreq provenance-graph --requirement-ir requirement.ir.json --out provenance.json
uv run nlreq clarify --agreement translation-agreement-input.json --out clarifications.json
uv run nlreq apply-clarification --controlled requirement.nlreq3 \
  --response clarification-response.json --out clarified.json
```

## Invariants

- Previous controlled text remains hash-addressed.
- Clarification changes are span-targeted.
- Unsupported formal fragments identify their IR node when available.

## Exit Criteria

Translator disagreement and unsupported lowering can produce UI-ready
clarification data.

## Implementation Spec

Input artifacts:

- `RequirementIRV2` with source spans.
- Optional `LoweredFormalArtifact` with diagnostics.
- Structural or logical translation agreement reports that contain
  clarification questions.

Output artifacts:

- `ProvenanceGraph` with text-span, IR-node, formal-fragment, and refusal
  nodes.
- `ClarificationRequest` artifacts grounded in target nodes or spans.
- `ClarificationResponse` artifacts from reviewers.
- `ClarifiedControlledText` preserving previous and new text hashes.

Graph semantics:

- Text spans connect to IR nodes with `parsed_to`.
- IR nodes connect to lowered formal artifacts with `lowered_to`.
- Unsupported formal diagnostics connect IR nodes to refusal reasons with
  `refuses`.

Clarification semantics:

- Clarification requests are generated from translator disagreement and can be
  displayed directly by product surfaces.
- Responses apply exact character-span replacements.
- Applying a response does not mutate prior artifacts; it creates a new
  controlled text version.

Failure modes:

- Invalid replacement spans raise before a clarified artifact is produced.
- Unsupported formal fragments without known IR nodes remain stage-level
  diagnostics until a later phase can attach them.

Tests:

- `tests/test_milestone_group1.py` verifies graph construction and targeted
  clarification response hashing.
