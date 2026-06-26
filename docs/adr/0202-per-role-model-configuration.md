# ADR 0202: Per-Role Model Configuration And Resolution Ladder

## Status

Accepted

## Context

nlreq uses an LLM in five distinct roles — drafting, decomposition, impact estimation,
spec extraction, and ensemble audit. Until now each role reached a pinned module constant
(`_DEFAULT_MODEL`, `_DEFAULT_DECOMPOSITION_MODEL`, `_DEFAULT_AUDIT_MODEL`) with no
configuration surface: no environment override, no config file, and no per-role selection
object. Only two commands accepted a per-call `--model`, and the ensemble/audit paths
hard-coded `AnthropicDecompositionClient()` / `AnthropicAuditClient()` with no way to
diverge the model per role.

The nlreq scope *Per-Role Model Config + CLI-Backed Cross-Provider LLM Adapter* (Work
Item 1) requires a role → (client kind, model) configuration object with a resolution
ladder, a single factory as the CLI's construction point, per-role provenance, and a
default-transport decision — without changing behaviour when nothing is configured.

## Decision

Introduce `src/nlreq/model_config.py` with:

1. **Roles and kinds.** A `Role` enum (`drafting`, `decomposition`, `impact`,
   `extraction`, `audit`) and a `ClientKind` enum (`anthropic`, `cli`, `recorded`).
   `drafting`/`impact`/`extraction` share the `LlmClient` protocol but are distinct
   roles so a project can pick a heavy drafter and a lite impact estimator independently.

2. **Resolution ladder (highest wins).** per-call override (`--model` / `--fixture` /
   the `live:<model>` / `recorded:<path>` ensemble schemes) → `NLREQ_<ROLE>_*` env vars
   → `nlreq-models.toml` (via `--model-config` or `NLREQ_MODEL_CONFIG`) → the pinned
   module constants. This mirrors the operator `models.env` conditional-assignment
   philosophy: process env wins over the file default.

3. **Single construction point.** `build_client_for_role(role, config, *, model=None,
   fixture=None)` returns a `BuiltClient` pairing the client with a `RoleProvenance`
   record. The `intake-draft` (drafting) and `semantic-translate` (decomposition +
   audit) CLI commands construct clients exclusively through this factory.

4. **Byte-stability of the default path.** When nothing is configured, the factory
   reproduces the exact `Anthropic*Client(model=<pinned default>)` construction and the
   exact provenance bytes the CLI emitted before. New provenance fields
   (`client_kind` / `prompt_version` / `wrapper`) are recorded ONLY when a non-default
   rung resolves, so default-path artifacts stay byte-identical (acceptance #1). The
   `AnthropicDecompositionClient` emits `client_kind` into its provenance dict only when
   a non-default rung resolved (`client_kind=None` on the default path).

5. **Structured refusals.** Unknown role/kind, the not-yet-wired `cli` kind, a missing
   or malformed recorded fixture, and an invalid config file all raise
   `ModelConfigError`, which the CLI surfaces as exit 2. The factory never degrades to a
   silently-different client.

6. **Default-transport decision.** The shipped zero-config default transport is
   **Anthropic**. The Messages API response carries the exact model snapshot id — the
   highest-precision provenance, which is what an attestation tool's default should be.
   Operators make `cli` their *effective* default via machine-level config/env (one-time,
   wins over the file default). **Transport auto-detection with fallback is PROHIBITED:**
   a transport silently different from the configured one is the same provenance hazard as
   a silent model fallback.

## Alternatives Considered

- **Auto-detect the cli transport when a wrapper is present, else fall back to the API.**
  Rejected: a transport silently different from the configured one is a provenance hazard
  in an attestation context. The operator must opt into a transport explicitly; the
  factory refuses the `cli` kind until `CliLlmClient` (Work Item 2) lands rather than
  silently using the API.

- **Record `client_kind` on the default path too.** Rejected for now: it would change the
  default-path artifact bytes, violating the "zero behaviour change when nothing is
  configured" invariant. The fields appear only when configuration is active, which is
  exactly when provenance diversity matters. (The live Anthropic path is never exercised
  in CI, so this is a contract choice, not a test-preservation hack.)

- **Per-call `--model` only, no config object.** Rejected: it cannot express a per-role
  default (e.g. a heavy drafter + lite impact model) and gives operators no machine-level
  configuration surface, which is the stated gap.

## Consequences

- The CLI has one client-construction point (`build_client_for_role`), making it trivial
  to add the `cli` transport (Work Item 2) and the `cli:` ensemble scheme + impact/
  extraction live-client exposure (Work Item 3) as extensions to the factory rather than
  new ad-hoc construction sites.
- Per-role provenance (`client_kind`, `prompt_version`, `wrapper`) is now recordable in
  the proposal/DecompositionResult artifacts when configuration is active, enabling the
  cross-provider agreement evidence of acceptance #2 once the cli transport lands.
- The audit role's CLI transport is wired (Work Item 3): `CliLlmClient` implements the
  `AuditClient` protocol, so `--audit-client cli:<wrapper>` runs a cross-provider audit. The
  `AuditVerdict` carries FULL CLI-transport provenance — `client_kind`, `provider`, `route`,
  `wrapper`, `wrapper_hash`, `cli_version` (populated from the validated sidecar by
  `CliLlmClient.audit_decomposition`), in addition to `model_id` (the sidecar-resolved model id —
  which provider audited). These fields are byte-stable (optional, None-default, serialized with
  `exclude_none=True`), so existing anthropic/recorded audit artifacts are unchanged; the full
  verdict is content-addressed by the provenance graph node's `artifact_hash` and serialized in
  the report's `ensemble_candidate_audit_verdicts`. Audit kind is implied by `client_kind`
  (anthropic/cli/recorded), with the cli audit's resolved model id recorded in `model_id`. The
  previously-deferred widening was subsequently implemented; the `AuditVerdict` carrier is
documented in ADR 0205.
- Follow-on ADRs: 0203 (CLI transport + pure-completion contract + sidecar provenance)
  and 0204 (cross-provider ensemble and audit policy with per-role calibrated operating
  points).
