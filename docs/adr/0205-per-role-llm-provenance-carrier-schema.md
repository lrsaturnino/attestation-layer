# ADR 0205: Per-Role LLM Provenance Carrier Schema

## Status

Accepted

## Context

ADR 0202 introduced per-role LLM provenance (`client_kind`, `resolved_model`,
`prompt_version`, `wrapper` identity) and ADR 0203 added the CLI transport's sidecar
provenance (`provider`, `route`, `wrapper_hash`, `cli_version`). The scope (§3) requires
that "the package/proposal artifacts record, per role: client kind, resolved model id,
prompt version, and (for cli) wrapper identity … Extend the relevant schemas (`schemas/`)
where the slots don't exist; never widen an existing meaning."

The review of the prior iteration flagged that no `schemas/` file was extended: the
per-role provenance rides the *untyped* `metadata: dict[str, str]` slot already present on
`CandidateSpecProvenance` (extraction), `RewriteProducerMetadata` (drafting), and the
production-source-impact report (impact), leaving the provenance contract unenforced by
the schema. This ADR records the deliberate decision and its boundary.

## Decision

**The generic `metadata: dict[str, str]` slot is the intended carrier for per-role LLM
provenance; the schemas are NOT widened with typed per-role fields.**

Rationale:

1. **The schemas already permit it.** Every carrier slot is declared
   `{"type": "object", "additionalProperties": {"type": "string"}}`
   (`spec-extraction-workbench.schema.json`, `specula-extraction-integration-report.schema.json`,
   `production-source-impact-report.schema.json`, `controlled-rewrite-proposal.schema.json`).
   The well-known per-role keys pass schema validation today; no slot is missing.

2. **Byte-stability of the default path (acceptance #1).** Widening the schemas with
   REQUIRED typed fields would force every artifact — including default-path artifacts that
   must stay byte-identical — to carry them, violating the "zero behaviour change when
   nothing is configured" invariant. Making them OPTIONAL typed fields adds schema surface
   for no enforcement gain (an absent field is already the default-path signal). The
   `metadata` slot keeps the keys absent on the default path and present only when a
   non-default rung resolves — exactly the byte-stability contract.

3. **"Never widen an existing meaning" is honored.** The `metadata` slot already carried
   free-form string metadata (e.g. `module_id`, `extraction`, `slither_status`); the
   per-role LLM keys are ADDITIONAL string keys in the same slot, not a redefinition of an
   existing key's meaning. No existing key's semantics change.

### Well-known per-role LLM provenance keys

The contract is the well-known key SET stamped into `metadata` (all `str` values), enforced
by tests rather than by schema closure:

| Key | Transport | Meaning |
|---|---|---|
| `client_kind` | all (non-default) | `anthropic` \| `cli` \| `recorded` |
| `prompt_version` | all (non-default) | the role's prompt-template version stamp |
| `resolved_model` | cli (sidecar); anthropic (extraction metadata) | the exact model id that answered — the sidecar-resolved id for cli, NEVER the tier |
| `wrapper` | cli | the wrapper basename |
| `provider` | cli (sidecar) | the provider that answered |
| `route` | cli (sidecar) | must equal the requested route (`official`) |
| `wrapper_hash` | cli (sidecar) | the wrapper content hash |
| `cli_version` | cli (sidecar) | the wrapper/CLI tool version |

For the decomposition role, the same fields are recorded in the TYPED
`DecompositionResult.provenance` dict (which is `dict[str, str]`), not the generic
`metadata` slot — decomposition has its own provenance carrier.

For the audit role, the same fields are recorded as TYPED OPTIONAL fields directly on the
`AuditVerdict` model (`client_kind`, `provider`, `route`, `wrapper`, `wrapper_hash`,
`cli_version`, plus `model_id` for the resolved model id), not the generic `metadata` slot —
audit has its own provenance carrier, parallel to decomposition. These fields are None-default
and serialized with `exclude_none=True`, so anthropic/recorded/default audit artifacts are
byte-identical (acceptance #1); the full verdict is content-addressed by the provenance graph
node's `artifact_hash` (`provenance.py`) and serialized in the report's
`ensemble_candidate_audit_verdicts`. `CliLlmClient.audit_decomposition` populates them from the
validated sidecar; `AnthropicAuditClient` sets only `model_id`. This is the previously-deferred
`AuditVerdict` widening referenced by ADR 0202 / ADR 0204 — now implemented.

### Provenance-integrity invariants (enforced in code + tests)

- **Default path stamps NONE of these keys** (byte-stability / acceptance #1).
- **cli provenance is stamped ONLY with a validated sidecar** — `client_kind=cli` /
  `wrapper` never appear without `resolved_model` / `provider` / `route` / `wrapper_hash`
  from a sidecar-backed call. An attestation client is never recorded as answering a call
  it never made (the extraction-command guard + the `_stamp_llm_role_provenance` sidecar
  check).
- **Per-role provenance is stamped ONLY onto artifacts an LLM call produced.** A
  placeholder / missing-input extraction candidate (`llm_draft_used=False`) carries NONE of
  these keys.

## Alternatives Considered

- **Widen the schemas with typed per-role fields.** Rejected: it is a byte-stability risk
  for the default path (acceptance #1) and gains no enforcement — the keys are optional
  either way, and the well-known-key SET is the real contract, enforced by tests. The
  generic `metadata` slot is the natural carrier and is already permitted.

- **A separate typed `llm_provenance` object on each carrier.** Rejected for now: it would
  widen every carrier schema (byte-stability risk) and duplicate information already
  carried in `metadata`. If a future change needs structured per-role provenance (e.g. for
  cross-artifact querying), it can be added as a new OPTIONAL object without disturbing the
  `metadata` keys.

## Consequences

- The per-role LLM provenance contract is the well-known key SET in `metadata`, asserted by
  tests (`tests/test_cli_llm_client.py`, `tests/test_model_config.py`,
  `tests/test_spec_extraction.py`): the keys are present on the cli path and absent on the
  default path / non-LLM-produced candidates.
- No schema change is required; the existing `additionalProperties: {type: string}`
  carriers remain the validation surface. A wrapper that omits a sidecar field is refused
  by the fail-closed `CliLlmClient` sidecar validation (ADR 0203), not by the schema.
- The decomposition role continues to use its own typed `DecompositionResult.provenance`
  dict; the audit role uses typed optional fields on `AuditVerdict`; this ADR's `metadata`-slot
  carriers are drafting / impact / extraction.
