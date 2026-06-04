# Review — iter 7
## Implementation summary
This iteration addressed the three recommended actions from iter 6: PA-4 real client, PA-5 FormalClaim-signature comparator + refusal wiring, and gate de-fabrication.

### PA-4 — Real `AnthropicLlmClient`
- Added `AnthropicLlmClient` to `src/nlreq/llm_client.py:68-108`: lazy `import anthropic` inside `propose_controlled_rewrite`; credentials loaded from `NLREQ_ANTHROPIC_API_KEY` via `load_api_key()` (credential check before import, so missing key → `EnvironmentError`, not `ImportError`).
- Added `anthropic>=0.25` as an optional dep in `pyproject.toml` under `[project.optional-dependencies] llm`.
- Wired `intake-draft --method llm` (no `--fixture`) to use `AnthropicLlmClient` (`src/nlreq/cli.py:2028-2033`).
- Removed misleading `llm` choice from `draft-controlled --method` (`src/nlreq/cli.py:480`).
- Removed stale `PA-4.T2 TODO` from `src/nlreq/intake.py`.

**Limitation acknowledged**: `NLREQ_ANTHROPIC_API_KEY` is not set in this repo's environment (`.claude/.env` has `TG_BOT_*` and `ENRICHER_*` only) and `anthropic` is an optional dep not installed by default. The real client requires operator-set `NLREQ_ANTHROPIC_API_KEY` + `pip install .[llm]`; not exercisable in CI by design. Offline path (`--fixture`) remains fully functional.

### PA-5 — FormalClaim-signature comparator + REFUSED_AMBIGUOUS
- Updated `_disagreements()` in `src/nlreq/translator_agreement.py:125-195` to use `formal_claim_signature(claim, alpha_identifiers=True, commutative=True)` as the primary agreement predicate when both candidates lower to a `FormalClaim`; structural diff used only when one or both fail to lower.
- Added `refuse_ambiguous_ensemble()` to `src/nlreq/semantic_translation.py`: emits `SemanticTranslationReport` with `result="refused"`, `refusal_code="NLR-REFUSED-AMBIGUOUS"`, `syntactically_valid=True`, and clarification questions mapped from disagreement paths.

### Gate de-fabrication + PA-5 live wiring
- Single-source IR branch now uses one candidate → `needs_review` (no fabricated `agreed`) in `src/nlreq/end_to_end_gate.py:233-246`.
- Added `translation_agreement: TranslationAgreementInput | None = None` param to `run_end_to_end_requirement_gate` (`src/nlreq/end_to_end_gate.py:215`). When supplied, it is used instead of auto-generated candidates.
- Added live wiring: when `translation.status == "disagreed"`, calls `refuse_ambiguous_ensemble` and records `translation_refusal` artifact with `NLR-REFUSED-AMBIGUOUS`; existing `_blockers` propagates this to `decision="refused"` (`src/nlreq/end_to_end_gate.py:281-285`).
- Controlled_text branch kept as two independent DSL v2 parse invocations (genuinely separate `parse_ir` calls, not same object reference).

## Tests added (13 new, total 492 passing up from 479)
- `test_anthropic_llm_client_constructs_without_key_in_env` — construction does not read the key (lazy)
- `test_anthropic_llm_client_raises_on_missing_key` — `EnvironmentError` on missing key
- `test_anthropic_llm_client_raises_on_empty_key` — `EnvironmentError` on empty/whitespace key
- `test_anthropic_llm_client_is_llm_client_protocol` — satisfies `LlmClient` Protocol
- `test_intake_draft_llm_no_fixture_constructs_real_client` — CLI with missing key → non-zero exit + variable name in stderr (not `NotImplementedError`)
- `test_load_api_key_requires_env_var` / `test_load_api_key_returns_key_from_env`
- `test_anthropic_llm_client_response_parsing` — monkeypatches fake `anthropic` module; verifies `message.content[0].text` extraction
- `test_gate_single_source_ir_yields_needs_review_not_agreed` — asserts the artifact status is `needs_review`
- `test_gate_refuses_on_disagreeing_translation_agreement_input` — genuinely disagreeing `TranslationAgreementInput` → `decision="refused"` + `NLR-REFUSED-AMBIGUOUS` in `translation_refusal` artifact
- `test_translation_agreement_agrees_on_alpha_equivalent_formal_claims` — same structure, different operand names → `agreed` under `alpha_identifiers=True`
- `test_translation_agreement_uses_formal_claim_signature_for_v3_requirements` — auth vs. numeric_invariant → `disagreed` with "formal-claim" in reason
- `test_refuse_ambiguous_ensemble_emits_refused_ambiguous_code` — unit tests refusal report shape

## Issues that persist
- **PA-1/PA-2 acceptance still unmet**: lowering is non-vacuous scaffolding but not checker-distinguishable under `S ∧ R` (`tests/test_translator.py:582-585` still documents this).
- **PA-5 spike not yet run**: 30-item spike on false-agreement/false-refusal rates across two domains not implemented.
- **PA-6 audit gate still absent**: no second-model audit rubric or per-fragment LLM-vs-deterministic provenance gate.
- **PA-7/PA-8 still the old contradiction table**: `contradiction_type` only allows `opposite_predicate`; seven-class taxonomy not implemented.
- **PA-9 corpus still seed-sized**: three items, not ≥30 per domain; benchmark harness does not run the prose→controlled→IR path.

## Recommended actions
- Implement PA-6: add `second_model_audit` rubric + gate in `translator_workbench.py`; tag LLM vs. deterministic per fragment in `provenance.py`; add test that a planted invented-premise decomposition is caught.
- Expand translation corpus (`benchmarks/requirements-translation/corpus.json`) to ≥30 items in two unrelated domains; wire `translation_benchmark.py` to run the PA-4/PA-5 prose→controlled→IR front half rather than consuming precomputed result JSON (`src/nlreq/cli.py:3311-3323`).
- Replace legacy contradiction table in `system_checker.py:217-246` with the seven-class FormalClaim taxonomy; wire numeric-range / temporal checks via SMT.
- Either close PA-1/PA-2 by running a real Apalache binary check on the lowered `authorization_precondition` module, or explicitly mark them "deferred pending Pillar B" in the test comments.
