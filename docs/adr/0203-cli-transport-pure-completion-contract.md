# ADR 0203: CLI Transport, Pure-Completion Contract, And Sidecar Provenance

## Status

Accepted (iter-2 strengthening: always-on wrapper-executable hash verification
and relative-wrapper-path resolution — see Decision)

## Context

Work Item 1 (ADR 0202) gave nlreq a per-role model configuration and a single construction
factory, but the only live transport was the in-process Anthropic SDK. The operator already
runs a mature, tiered, multi-provider CLI harness (`run-claude` / `run-gpt` / `run-gemini` /
`run-oss` / `run-oss-local`) with centralized model resolution in `models.env`. The scope
asks: use that harness as nlreq's cross-provider transport, so an ensemble agreement gate can
finally compare models from *different* families — correlated training bias is exactly what a
same-provider agreement gate cannot catch.

The operator's wrappers were built for *agentic* work (ralph, ACP, review rosters), where tool
use, repo context, and soft fallback are features. In an attestation context each is a
provenance hazard: a drafting call that can touch the filesystem, that is silently steered by
CLAUDE.md/cwd, or that silently answers from a different provider than requested, produces
evidence with unverifiable origin — exactly what nlreq exists to reject.

## Decision

Add `src/nlreq/cli_llm_client.py` with `CliLlmClient`, which implements the `LlmClient`
protocol (drafting / impact / extraction — three methods), the `DecompositionClient` protocol
(one method), AND the `AuditClient` protocol (one method) — five methods total — so it is the
CLI transport for all five roles. It shells out to an operator wrapper executable, the same
anti-corruption subprocess pattern nlreq uses for every external verifier (slither, foundry, go,
model-checker). Auth stays in the operator's `.env`, sourced by the wrapper; nlreq never touches
provider keys.

Every call runs under a **pure-completion contract**:

1. **No tools.** The env requests no tools (`PI_TOOLS=""`); the sidecar's `tools_active` flag
   is the enforced guard, because some wrappers currently ignore an empty tool list (run-oss
   falls back to the full set). A wrapper whose sidecar reports `tools_active=true` is refused
   — attestation-ineligible until the operator adds a real no-tools knob (scope §6).
2. **No repo/cwd context.** The wrapper runs in a scratch *empty* working directory so
   CLAUDE.md / settings / hooks auto-load finds nothing to steer the model. The configured
   wrapper path is resolved to an ABSOLUTE executable path (`shutil.which` + `os.path.abspath`)
   BEFORE the scratch-cwd switch, so a relative wrapper (e.g. `./.claude/bin/run-gpt`) is found
   in the invocation directory rather than looked up in the scratch temp dir (iter-2 fix — a
   relative path previously escaped the `CliTransportError` structured-refusal contract with
   an uncaught `FileNotFoundError`).
3. **No silent fallback.** `OSS_SOFT_FALLBACK=0` and `OSS_FORCE_OPENROUTER` unset; the sidecar's
   `route` must equal the requested route, else the recorded model would be a lie.
4. **Resolved-model provenance, never the tier.** Explicit model-env exports win over the
   wrapper's `models.env` defaults, and the sidecar's `resolved_model` (the exact id that
   answered) is what provenance records.

A wrapper-side `<output>.meta.json` sidecar (scope §6, operator repo) is **required** for every
call. Missing/invalid sidecar, `route != requested`, `tools_active=true`, a missing
`resolved_model`, or a wrapper-hash mismatch each raise `CliTransportError` — the client
refuses rather than fakes, with the same blocking `tool_error` semantics as the solver clients.
`CliTransportError` subclasses `ModelConfigError` (a `ValueError`), so the CLI's existing
`except ValueError` handlers catch it.

**Always-on wrapper-executable hash verification (iter-2 strengthening).** The sidecar's
`wrapper_hash` is NOT a self-reported claim. nlreq independently computes the SHA-256 of the
resolved wrapper executable (`_sha256_file` — the raw hexdigest of the file's bytes, no
`sha256:` prefix, matching the operator wrappers' `_script_sha256` /
`shasum -a 256 <path> | cut -d' ' -f1`) BEFORE invoking the wrapper, and requires the sidecar's
`wrapper_hash` to equal it on EVERY call. This anchors provenance to the executable that
actually ran: a wrapper that emits a stale/fake hash is refused even when no caller-supplied
`expected_wrapper_hash` pin was supplied, defeating wrapper drift (an edited wrapper changes
behaviour under a recorded identity). The eligible wrappers (run-claude / run-gpt) already
report their own file hash via `_script_sha256`, so they pass; the offline echo-wrapper
conformance suite mirrors this (each echo wrapper computes its own hash, and the tests assert
the recorded hash equals `sha256(wrapper file)`).

The optional `expected_wrapper_hash` constructor pin is retained as a known-good-version guard:
the always-on check proves `sidecar.wrapper_hash == executable hash`, so the pin additionally
asserts `executable hash == pinned known-good hash`, catching a swapped wrapper even if the
sidecar honestly reports the new (different) hash. The factory/CLI do not currently set it; it
is a defensive pin for future config-driven version pinning.

The drafting/impact/extraction prompt builders were lifted out of `AnthropicLlmClient` into
shared module-level versioned templates (`build_drafting_prompt` /
`build_impact_estimate_prompt` / `build_spec_extraction_prompt`, each with a `_*_PROMPT_VERSION`
stamp). Both transports call the same builders, so a prompt fork between the API and CLI
transports is impossible, and `prompt_hash` values are stable across the lift (the text is
byte-identical).

The factory's `cli` kind now constructs `CliLlmClient` for drafting/impact/extraction/
decomposition/audit (all five roles); the `cli:<wrapper>[:<tier-or-model>]` ensemble/audit
scheme (a new `CliOverride` rung, the highest in the ladder) makes the cross-provider
decomposition ensemble and the cross-provider audit reachable from the CLI. The `cli:` suffix
grammar is unambiguous: a bare `heavy|lite|tiny` is tier shorthand; `tier=<t>` / `model=<id>`
are explicit (at most one of each, in any order); any other bare suffix is REJECTED as
ambiguous. `model=<id>` is a *verification* guard — the operator wrappers resolve models from
wrapper+tier-specific env vars sourced from `models.env` (conditional-assignment form → process
env wins), so the per-call scheme cannot pin a model via env without wrapper-specific knowledge
(that is the config/env `model_env` rung's job); instead the fail-closed sidecar check refuses if
the wrapper resolved a model other than the one the scheme required, so provenance records the
sidecar-resolved id, never the tier (scope §4). A decomposition ensemble of `cli:run-A` +
`cli:run-B` records two distinct providers, resolved model ids, wrapper hashes, and prompt
versions in the report's `ensemble_candidate_provenances` (acceptance #2). `--audit-client
cli:<wrapper>[:<tier-or-model>]` runs a cross-provider audit whose `AuditVerdict.model_id` is the
sidecar-resolved model id (ADR 0204).

## Alternatives Considered

- **Import N provider SDKs in-process.** Rejected: nlreq already reaches every external
  verifier through recorded subprocess clients; an LLM-CLI client is the same anti-corruption
  pattern, arguably more consistent than the in-process `import anthropic`. Auth and model
  resolution stay in the operator's harness.
- **Auto-detect the cli transport when a wrapper is present, else fall back to the API.**
  Rejected (as in ADR 0202): a transport silently different from the configured one is a
  provenance hazard. The transport is selected explicitly via config/env/`cli:` scheme.
- **Trust the wrapper without a sidecar.** Rejected: without a machine-readable record of what
  actually answered (provider, resolved model, route, tools), the recorded model could be a lie.
  The sidecar + route/tools/hash guards make the origin verifiable.

## Consequences

- nlreq gains a cross-provider transport without adding provider SDKs, and the ensemble
  agreement gate can finally compare models from different families. The trust model is
  unchanged: LLM output remains proposal-only on every transport; no auto-acceptance anywhere.
- The operator must emit the `<output>.meta.json` sidecar (scope §6) and add real no-tools /
  no-context knobs to each wrapper (or mark it attestation-ineligible). Until then, real-wrapper
  tests skip (`NLREQ_RUN_REAL_WRAPPER_TESTS=1` opt-in); the offline echo-wrapper conformance
  suite pins the contract. This is the remaining cross-repo dependency.
- Drafting/impact/extraction CLI-transport provenance (the sidecar's resolved model) IS recorded
  in those roles' artifacts: after a successful cli call the CLI merges
  `CliLlmClient.last_call_provenance()` (resolved_model / provider / route / wrapper /
  wrapper_hash / cli_version) into the produced artifact's metadata (ADR 0204 §3). A
  provenance-integrity guard refuses the extraction commands when `--llm-client` is supplied but
  no LLM call ran (no Specula extractor for the language, or required inputs missing), and stamps
  per-role provenance ONLY onto candidates an LLM call actually produced (`llm_draft_used=True`);
  for the cli transport nothing is stamped without a validated sidecar. An attestation client is
  never recorded as answering a call it never made. The decomposition role records full sidecar
  provenance directly in its `DecompositionResult.provenance`.
- Follow-on: ADR 0204 (cross-provider ensemble and audit policy, per-role calibrated operating
  points, and the operator wrapper-side §6 contract) covers the calibration run and the remaining
  cross-repo wrapper dependencies.
