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
