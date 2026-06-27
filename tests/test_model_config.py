"""Tests for Work Item 1 (nlreq per-role model configuration): the resolution ladder,
the single construction factory, per-role provenance, structured refusals, and the
byte-stability of the default path (acceptance #1: zero behaviour change when nothing
is configured).

These tests are CI-safe: they never call a live model. The Anthropic*Client objects
are constructed (no API key needed for construction) and their resolved config/provenance
is asserted; the recorded transports are exercised through real fixtures; and the
not-yet-wired ``cli`` kind is asserted to refuse rather than fall back to the API.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from nlreq.audit_client import (
    AuditVerdict,
    RecordedAuditClient,
    RecordedAuditFixture,
)
from nlreq.cli import main
from nlreq.decomposition_client import (
    AnthropicDecompositionClient,
    DecompositionResult,
    RecordedDecompositionClient,
    _DEFAULT_DECOMPOSITION_MODEL,
    _DECOMPOSITION_PROMPT_VERSION,
)
from nlreq.dsl_v3 import DslV3Parser
from nlreq.intake import (
    create_free_form_intake,
    draft_controlled_rewrite_with_llm,
)
from nlreq.jsonutil import sha256_text
from nlreq.llm_client import (
    AnthropicLlmClient,
    RecordedLlmClient,
    _DEFAULT_MODEL,
    _DRAFTING_PROMPT_VERSION,
)
from nlreq.model_config import (
    CONFIG_PATH_ENV,
    ClientKind,
    ModelConfig,
    ModelConfigError,
    Role,
    build_client_for_role,
    load_model_config,
)
from nlreq.audit_client import _DEFAULT_AUDIT_MODEL, _AUDIT_PROMPT_VERSION


# A valid DSL v3 controlled text (same shape the offline LLM tests use) for building
# decomposition fixtures and driving the recorded drafting path.
_CONTROLLED = (
    "requirement authorization_precondition:\n"
    "scope operation\n"
    "when actor is not authorized\n"
    "then operation must reject before state_change\n"
)
_PROSE = "Unauthorised actors must be blocked before any state change occurs."

_FIXTURE_REQUIREMENT = Path(__file__).parent / "fixtures" / "requirements" / "authorization_precondition_v3.nlreq"


def _parse_ir() -> object:
    """Parse a known-good controlled text into a RequirementIRV2 for fixture building."""
    return DslV3Parser().parse_ir(
        _FIXTURE_REQUIREMENT.read_text(), requirement_id="R-MC", title="model-config test"
    )


def _no_role_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Strip every NLREQ_<ROLE>_* env var so a test's ladder starts from a clean baseline."""
    for role in Role:
        prefix = f"NLREQ_{role.name.upper()}"
        for suffix in ("CLIENT", "MODEL", "WRAPPER", "TIER", "FIXTURE", "MODEL_ENV", "TIMEOUT_S"):
            monkeypatch.delenv(f"{prefix}_{suffix}", raising=False)
    monkeypatch.delenv(CONFIG_PATH_ENV, raising=False)


# ---------------------------------------------------------------------------
# Resolution ladder (golden fixtures): override → env → file → pinned default
# ---------------------------------------------------------------------------


def test_default_model_constants_are_the_scoped_baseline() -> None:
    """The pinned default constants must equal the scoped baseline literal.

    Acceptance #1 requires unchanged no-config defaults. The ladder tests above import
    these same constants and assert against them, which is self-referential — a bump to
    ``claude-opus-4-8`` would pass those tests too. This test pins the LITERAL value so a
    default bump cannot hide: it is the byte-stability anchor the scope demands.
    """
    assert _DEFAULT_MODEL == "claude-haiku-4-5-20251001"
    assert _DEFAULT_DECOMPOSITION_MODEL == "claude-haiku-4-5-20251001"
    assert _DEFAULT_AUDIT_MODEL == "claude-haiku-4-5-20251001"


@pytest.mark.parametrize("role", list(Role))
def test_default_resolution_is_pinned_anthropic_constant(
    monkeypatch: pytest.MonkeyPatch, role: Role
) -> None:
    """Lowest rung: no override/env/config → anthropic + the role's pinned default model.

    This is the byte-stability anchor (acceptance #1): the factory's default path must
    reproduce the exact pre-config construction. is_default=True and as_metadata() is
    empty so default-path artifacts gain no new provenance fields.
    """
    _no_role_env(monkeypatch)
    built = build_client_for_role(role, None)
    assert built.provenance.client_kind is ClientKind.anthropic
    assert built.provenance.is_default is True
    assert built.provenance.source == "default"
    assert built.provenance.as_metadata() == {}

    expected_model = {
        Role.drafting: _DEFAULT_MODEL,
        Role.impact: _DEFAULT_MODEL,
        Role.extraction: _DEFAULT_MODEL,
        Role.decomposition: _DEFAULT_DECOMPOSITION_MODEL,
        Role.audit: _DEFAULT_AUDIT_MODEL,
        Role.partition: _DEFAULT_MODEL,
    }[role]
    assert built.provenance.resolved_model == expected_model


def test_per_call_model_override_wins_over_env_file_default(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A per-call model override is the highest rung: it beats env, file, and default."""
    _no_role_env(monkeypatch)
    monkeypatch.setenv("NLREQ_DECOMPOSITION_MODEL", "env-model")
    monkeypatch.setenv("NLREQ_DECOMPOSITION_CLIENT", "anthropic")
    cfg = load_model_config(_write_config(tmp_path, {"decomposition": {"client": "anthropic", "model": "file-model"}}))

    built = build_client_for_role(Role.decomposition, cfg, model="override-model")
    assert built.provenance.client_kind is ClientKind.anthropic
    assert built.provenance.resolved_model == "override-model"
    assert built.provenance.source == "override"
    assert built.provenance.is_default is False


def test_per_call_fixture_override_selects_recorded(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A per-call fixture override selects the recorded kind, short-circuiting the ladder."""
    _no_role_env(monkeypatch)
    fixture = tmp_path / "draft.txt"
    fixture.write_text(_CONTROLLED)
    built = build_client_for_role(Role.drafting, None, fixture=fixture)
    assert built.provenance.client_kind is ClientKind.recorded
    assert built.provenance.source == "override"
    assert built.provenance.is_default is False
    assert isinstance(built.client, RecordedLlmClient)


def test_env_wins_over_file_and_default(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """NLREQ_<ROLE>_* env vars beat the config file and the pinned default."""
    _no_role_env(monkeypatch)
    monkeypatch.setenv("NLREQ_AUDIT_CLIENT", "anthropic")
    monkeypatch.setenv("NLREQ_AUDIT_MODEL", "env-audit-model")
    cfg = load_model_config(_write_config(tmp_path, {"audit": {"client": "anthropic", "model": "file-audit-model"}}))

    built = build_client_for_role(Role.audit, cfg)
    assert built.provenance.resolved_model == "env-audit-model"
    assert built.provenance.source == "env"
    assert built.provenance.is_default is False


def test_file_wins_over_default(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """A config-file role spec beats the pinned default when no override/env is active."""
    _no_role_env(monkeypatch)
    cfg = load_model_config(_write_config(tmp_path, {"drafting": {"client": "anthropic", "model": "file-draft-model"}}))

    built = build_client_for_role(Role.drafting, cfg)
    assert built.provenance.resolved_model == "file-draft-model"
    assert built.provenance.source == "config-file"
    assert built.provenance.is_default is False
    assert isinstance(built.client, AnthropicLlmClient)


def test_override_wins_over_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Override (rung 1) beats env (rung 2)."""
    _no_role_env(monkeypatch)
    monkeypatch.setenv("NLREQ_DRAFTING_CLIENT", "anthropic")
    monkeypatch.setenv("NLREQ_DRAFTING_MODEL", "env-model")
    built = build_client_for_role(Role.drafting, None, model="override-model")
    assert built.provenance.resolved_model == "override-model"
    assert built.provenance.source == "override"


# ---------------------------------------------------------------------------
# Structured refusals (unknown role/kind, not-yet-wired cli, invalid fixtures/config)
# ---------------------------------------------------------------------------


def test_unknown_role_refuses(monkeypatch: pytest.MonkeyPatch) -> None:
    _no_role_env(monkeypatch)
    with pytest.raises(ModelConfigError, match="unknown role"):
        build_client_for_role("not-a-role")  # type: ignore[arg-type]


@pytest.mark.parametrize("role", [Role.drafting, Role.impact, Role.extraction, Role.partition])
def test_cli_kind_constructs_client_for_eligible_roles(
    monkeypatch: pytest.MonkeyPatch, role: Role
) -> None:
    """The cli kind constructs a CliLlmClient for the four eligible roles (Work Item 2).

    Construction never invokes the wrapper, so a configured cli role builds cleanly even
    with a wrapper that is not on PATH; the wrapper runs (and may refuse) only at call time.
    """
    from nlreq.cli_llm_client import CliLlmClient

    _no_role_env(monkeypatch)
    monkeypatch.setenv(f"NLREQ_{role.name.upper()}_CLIENT", "cli")
    monkeypatch.setenv(f"NLREQ_{role.name.upper()}_WRAPPER", "run-gpt")
    built = build_client_for_role(role, None)
    assert built.provenance.client_kind is ClientKind.cli
    assert isinstance(built.client, CliLlmClient)


def test_cli_kind_audit_constructs_client(monkeypatch: pytest.MonkeyPatch) -> None:
    """The audit role's cli transport is wired (Work Item 3): it constructs a CliLlmClient.

    ``CliLlmClient`` implements the ``AuditClient`` protocol (``audit_decomposition``),
    so a configured audit cli role builds cleanly; the wrapper runs (and may refuse) only
    at call time. Previously this was a structured refusal; completing the audit CLI
    transport (recommended action #8) makes cross-provider audit reachable.
    """
    from nlreq.cli_llm_client import CliLlmClient

    _no_role_env(monkeypatch)
    monkeypatch.setenv("NLREQ_AUDIT_CLIENT", "cli")
    monkeypatch.setenv("NLREQ_AUDIT_WRAPPER", "run-gpt")
    built = build_client_for_role(Role.audit, None)
    assert built.provenance.client_kind is ClientKind.cli
    assert isinstance(built.client, CliLlmClient)


def test_unknown_env_client_kind_refuses(monkeypatch: pytest.MonkeyPatch) -> None:
    _no_role_env(monkeypatch)
    monkeypatch.setenv("NLREQ_DRAFTING_CLIENT", "bogus")
    with pytest.raises(ModelConfigError, match="unknown NLREQ_DRAFTING_CLIENT"):
        build_client_for_role(Role.drafting, None)


def test_env_anthropic_without_model_refuses(monkeypatch: pytest.MonkeyPatch) -> None:
    _no_role_env(monkeypatch)
    monkeypatch.setenv("NLREQ_DRAFTING_CLIENT", "anthropic")
    with pytest.raises(ModelConfigError, match="requires NLREQ_DRAFTING_MODEL"):
        build_client_for_role(Role.drafting, None)


@pytest.mark.parametrize(
    "role, expected_client_type",
    [
        (Role.drafting, AnthropicLlmClient),
        (Role.decomposition, AnthropicDecompositionClient),
    ],
)
def test_env_model_only_resolves_as_anthropic_override(
    monkeypatch: pytest.MonkeyPatch, role: Role, expected_client_type: type
) -> None:
    """``NLREQ_<ROLE>_MODEL`` alone (``NLREQ_<ROLE>_CLIENT`` unset) resolves as an anthropic
    env-rung override — the documented resolution ladder honors a configured anthropic model
    when the client kind is unset (iter-2 BLOCKING fix). Previously ``_env_spec_for_role``
    returned ``None`` the moment the client var was unset, so a model-only env override fell
    through to the default and the configured model was silently ignored — violating the
    ladder and the ``_resolve`` docstring's promise that an anthropic model is honored when the
    client is unset/anthropic. Drafting (LlmClient) + decomposition (DecompositionClient) cover
    one LlmClient role and one non-drafting role, as the review required.
    """
    _no_role_env(monkeypatch)
    monkeypatch.setenv(f"NLREQ_{role.name.upper()}_MODEL", "env-only-model")
    built = build_client_for_role(role, None)
    assert built.provenance.client_kind is ClientKind.anthropic
    assert isinstance(built.client, expected_client_type)
    assert built.provenance.resolved_model == "env-only-model"
    assert built.provenance.source == "env"
    assert built.provenance.is_default is False
    # A non-default rung resolves → client_kind is recorded (unlike the byte-identical default).
    assert built.provenance.as_metadata()["client_kind"] == "anthropic"


def test_env_model_only_beats_config_file_and_default(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The model-only env override is the env rung, so it beats the config-file rung and the
    pinned default (iter-2 BLOCKING fix). A config file selecting a different anthropic model
    must NOT win over a model-only env override for the same role."""
    _no_role_env(monkeypatch)
    monkeypatch.setenv("NLREQ_DRAFTING_MODEL", "env-only-model")
    cfg = load_model_config(
        _write_config(tmp_path, {"drafting": {"client": "anthropic", "model": "file-draft-model"}})
    )
    built = build_client_for_role(Role.drafting, cfg)
    assert built.provenance.client_kind is ClientKind.anthropic
    assert built.provenance.resolved_model == "env-only-model"
    assert built.provenance.source == "env"
    assert isinstance(built.client, AnthropicLlmClient)


def test_env_model_only_honored_by_force_anthropic_live_scheme(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The bare ``live`` scheme (force_anthropic) honors a model-only env override too — forcing
    the KIND to anthropic does not discard a configured anthropic model id, whether the client
    var is set to anthropic or left unset (iter-2 BLOCKING fix). The ``_resolve`` docstring
    promises ``live`` honors an anthropic model when the client is unset/anthropic; the model-only
    fix makes the unset case true, not just the anthropic case."""
    from nlreq.cli import _resolve_client_scheme

    _no_role_env(monkeypatch)
    # No NLREQ_DECOMPOSITION_CLIENT — only the model env is set.
    monkeypatch.setenv("NLREQ_DECOMPOSITION_MODEL", "claude-sonnet-4-6")
    built = _resolve_client_scheme("live", Role.decomposition, ModelConfig())
    assert built.provenance.client_kind is ClientKind.anthropic
    assert isinstance(built.client, AnthropicDecompositionClient)
    assert built.provenance.resolved_model == "claude-sonnet-4-6"
    assert built.provenance.source == "env"
    assert built.provenance.as_metadata()["client_kind"] == "anthropic"


def test_env_cli_without_wrapper_refuses(monkeypatch: pytest.MonkeyPatch) -> None:
    _no_role_env(monkeypatch)
    monkeypatch.setenv("NLREQ_IMPACT_CLIENT", "cli")
    with pytest.raises(ModelConfigError, match="requires NLREQ_IMPACT_WRAPPER"):
        build_client_for_role(Role.impact, None)


def test_env_cli_model_env_pins_explicit_model_override(monkeypatch: pytest.MonkeyPatch) -> None:
    """``NLREQ_<ROLE>_MODEL_ENV`` (JSON object) pins explicit model ids that win over the
    wrapper's ``models.env`` defaults — the env-rung way to choose the resolved model by
    nlreq rather than the file default (recommended action #6)."""
    from nlreq.cli_llm_client import CliLlmClient

    _no_role_env(monkeypatch)
    monkeypatch.setenv("NLREQ_DRAFTING_CLIENT", "cli")
    monkeypatch.setenv("NLREQ_DRAFTING_WRAPPER", "run-gpt")
    monkeypatch.setenv("NLREQ_DRAFTING_MODEL_ENV", json.dumps({"GPT_LITE_MODEL": "gpt-4o-mini"}))
    built = build_client_for_role(Role.drafting, None)
    assert isinstance(built.client, CliLlmClient)
    assert built.client._model_env == {"GPT_LITE_MODEL": "gpt-4o-mini"}


def test_env_cli_timeout_pinned_into_client(monkeypatch: pytest.MonkeyPatch) -> None:
    """``NLREQ_<ROLE>_TIMEOUT_S`` overrides the default cli call timeout (env-rung cli spec)."""
    from nlreq.cli_llm_client import CliLlmClient

    _no_role_env(monkeypatch)
    monkeypatch.setenv("NLREQ_DRAFTING_CLIENT", "cli")
    monkeypatch.setenv("NLREQ_DRAFTING_WRAPPER", "run-gpt")
    monkeypatch.setenv("NLREQ_DRAFTING_TIMEOUT_S", "45.0")
    built = build_client_for_role(Role.drafting, None)
    assert isinstance(built.client, CliLlmClient)
    assert built.client._timeout_s == 45.0


def test_env_cli_model_env_invalid_json_refuses(monkeypatch: pytest.MonkeyPatch) -> None:
    """A malformed ``NLREQ_<ROLE>_MODEL_ENV`` is a structured refusal, not a silent ignore."""
    _no_role_env(monkeypatch)
    monkeypatch.setenv("NLREQ_DRAFTING_CLIENT", "cli")
    monkeypatch.setenv("NLREQ_DRAFTING_WRAPPER", "run-gpt")
    monkeypatch.setenv("NLREQ_DRAFTING_MODEL_ENV", "{not json")
    with pytest.raises(ModelConfigError, match="not valid JSON"):
        build_client_for_role(Role.drafting, None)


def test_missing_recorded_fixture_refuses(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _no_role_env(monkeypatch)
    missing = tmp_path / "does-not-exist.json"
    with pytest.raises(ModelConfigError, match="recorded fixture .* not found"):
        build_client_for_role(Role.drafting, None, fixture=missing)


def test_invalid_recorded_decomposition_fixture_refuses(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _no_role_env(monkeypatch)
    bad = tmp_path / "bad-decomp.json"
    bad.write_text("{not valid decomposition json}")
    with pytest.raises(ModelConfigError, match="not a valid DecompositionResult"):
        build_client_for_role(Role.decomposition, None, fixture=bad)


def test_invalid_recorded_audit_fixture_refuses(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _no_role_env(monkeypatch)
    bad = tmp_path / "bad-audit.json"
    bad.write_text("{not valid audit json}")
    with pytest.raises(ModelConfigError, match="not a valid RecordedAuditFixture"):
        build_client_for_role(Role.audit, None, fixture=bad)


def test_malformed_toml_refuses(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _no_role_env(monkeypatch)
    bad = tmp_path / "bad.toml"
    bad.write_text("this is = = not toml [")
    with pytest.raises(ModelConfigError, match="not valid TOML"):
        load_model_config(bad)


def test_config_unknown_role_key_refuses(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """A typo'd role name (extra='forbid' on ModelConfig) refuses rather than being ignored."""
    _no_role_env(monkeypatch)
    bad = tmp_path / "unknown-role.toml"
    bad.write_text("[draft]\nclient = 'anthropic'\nmodel = 'x'\n")
    with pytest.raises(ModelConfigError, match="invalid"):
        load_model_config(bad)


def test_config_spec_extra_key_refuses(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """A typo'd field in a role spec (extra='forbid' on the spec) refuses."""
    _no_role_env(monkeypatch)
    bad = tmp_path / "extra-key.toml"
    bad.write_text("[drafting]\nclient = 'anthropic'\nmoodel = 'x'\n")
    with pytest.raises(ModelConfigError, match="invalid"):
        load_model_config(bad)


def test_missing_config_file_refuses(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _no_role_env(monkeypatch)
    with pytest.raises(ModelConfigError, match="model config file not found"):
        load_model_config(tmp_path / "absent.toml")


# ---------------------------------------------------------------------------
# Provenance
# ---------------------------------------------------------------------------


def test_provenance_default_path_emits_no_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    _no_role_env(monkeypatch)
    built = build_client_for_role(Role.drafting, None)
    # Default path: empty metadata so the proposal stays byte-identical to the pre-config CLI.
    assert built.provenance.as_metadata() == {}
    assert built.provenance.is_default is True


def test_provenance_override_anthropic_records_client_kind_and_prompt_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _no_role_env(monkeypatch)
    built = build_client_for_role(Role.drafting, None, model="claude-x")
    meta = built.provenance.as_metadata()
    assert meta["client_kind"] == "anthropic"
    assert meta["prompt_version"] == _DRAFTING_PROMPT_VERSION
    # anthropic's model id is already recorded in producer.model — not duplicated here.
    assert "resolved_model" not in meta
    assert "wrapper" not in meta


def test_provenance_recorded_records_client_kind(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _no_role_env(monkeypatch)
    fixture = tmp_path / "draft.txt"
    fixture.write_text(_CONTROLLED)
    built = build_client_for_role(Role.extraction, None, fixture=fixture)
    meta = built.provenance.as_metadata()
    assert meta["client_kind"] == "recorded"
    assert meta["prompt_version"] == _DRAFTING_PROMPT_VERSION


def test_decomposition_client_kind_gating_is_byte_stable(monkeypatch: pytest.MonkeyPatch) -> None:
    """AnthropicDecompositionClient emits client_kind into provenance ONLY when non-default.

    Default path → client_kind None (provenance dict unchanged → byte-identical). A
    configured rung → client_kind 'anthropic' is emitted. This is the byte-stability
    gate for the decomposition transport.
    """
    _no_role_env(monkeypatch)
    default_built = build_client_for_role(Role.decomposition, None)
    assert isinstance(default_built.client, AnthropicDecompositionClient)
    assert default_built.client._client_kind is None  # default path: no client_kind key

    override_built = build_client_for_role(Role.decomposition, None, model="claude-x")
    assert isinstance(override_built.client, AnthropicDecompositionClient)
    assert override_built.client._client_kind == "anthropic"  # non-default: emitted


def test_prompt_version_per_role(monkeypatch: pytest.MonkeyPatch) -> None:
    """Each role's provenance carries its prompt-template version on a non-default rung."""
    _no_role_env(monkeypatch)
    assert build_client_for_role(Role.decomposition, None, model="x").provenance.prompt_version == _DECOMPOSITION_PROMPT_VERSION
    assert build_client_for_role(Role.audit, None, model="x").provenance.prompt_version == _AUDIT_PROMPT_VERSION
    assert build_client_for_role(Role.drafting, None, model="x").provenance.prompt_version == _DRAFTING_PROMPT_VERSION
    # The partition role (three-zone scope, Zone 1) carries its own versioned prompt.
    from nlreq.llm_client import _PARTITION_PROMPT_VERSION

    assert (
        build_client_for_role(Role.partition, None, model="x").provenance.prompt_version
        == _PARTITION_PROMPT_VERSION
    )


def test_partition_role_accepted_without_weakening_existing_roles(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The sixth ``partition`` role (three-zone scope §3) is accepted like the other LlmClient roles.

    Regression guard: partition is an LlmClient role (text in/out) that shares the drafting
    default model and resolves through the same four-rung ladder, so the existing five roles'
    resolution is unchanged. partition builds an ``AnthropicLlmClient`` on the default path and a
    ``CliLlmClient`` on the cli path, and its client implements ``propose_candidate_rules``.
    """
    from nlreq.cli_llm_client import CliLlmClient
    from nlreq.llm_client import AnthropicLlmClient

    _no_role_env(monkeypatch)

    # Default path: anthropic + the shared LlmClient default model + is_default.
    built = build_client_for_role(Role.partition, None)
    assert built.provenance.client_kind is ClientKind.anthropic
    assert built.provenance.is_default is True
    assert built.provenance.resolved_model == _DEFAULT_MODEL
    assert isinstance(built.client, AnthropicLlmClient)
    # partition is an LlmClient role: its client implements the partition proposal method.
    assert hasattr(built.client, "propose_candidate_rules")

    # Per-call model override wins for partition just like drafting.
    override = build_client_for_role(Role.partition, None, model="override-partition")
    assert override.provenance.resolved_model == "override-partition"
    assert override.provenance.source == "override"

    # The cli path constructs a CliLlmClient for partition (it implements the protocol method).
    monkeypatch.setenv("NLREQ_PARTITION_CLIENT", "cli")
    monkeypatch.setenv("NLREQ_PARTITION_WRAPPER", "run-gpt")
    cli_built = build_client_for_role(Role.partition, None)
    assert cli_built.provenance.client_kind is ClientKind.cli
    assert isinstance(cli_built.client, CliLlmClient)

    # Regression: the existing five roles still resolve to their pinned defaults untouched.
    monkeypatch.delenv("NLREQ_PARTITION_CLIENT", raising=False)
    monkeypatch.delenv("NLREQ_PARTITION_WRAPPER", raising=False)
    five_role_models = {
        Role.drafting: _DEFAULT_MODEL,
        Role.impact: _DEFAULT_MODEL,
        Role.extraction: _DEFAULT_MODEL,
        Role.decomposition: _DEFAULT_DECOMPOSITION_MODEL,
        Role.audit: _DEFAULT_AUDIT_MODEL,
    }
    for role, expected in five_role_models.items():
        again = build_client_for_role(role, None)
        assert again.provenance.resolved_model == expected, role
        assert again.provenance.is_default is True, role


def test_config_partition_section_loads(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """A ``[partition]`` config section is accepted and resolves through the ladder (§3)."""
    _no_role_env(monkeypatch)
    cfg = load_model_config(_write_config(tmp_path, {"partition": {"client": "anthropic", "model": "cfg-partition"}}))
    built = build_client_for_role(Role.partition, cfg)
    assert built.provenance.client_kind is ClientKind.anthropic
    assert built.provenance.resolved_model == "cfg-partition"
    assert built.provenance.source == "config-file"


# ---------------------------------------------------------------------------
# Byte-stability of the default drafting path (acceptance #1)
# ---------------------------------------------------------------------------


def test_draft_default_extra_provenance_none_keeps_metadata_byte_identical() -> None:
    """draft_controlled_rewrite_with_llm with no extra provenance keeps metadata as before.

    The default path passes an empty/None extra_provenance so producer.metadata stays
    exactly {'source_language': <lang>} — no client_kind key — matching the pre-config CLI.
    """
    intake = create_free_form_intake(
        intake_id="INTAKE-MC", original_text=_PROSE, submitted_at="2026-06-01T00:00:00Z"
    )
    proposal = draft_controlled_rewrite_with_llm(
        intake=intake,
        client=RecordedLlmClient(_CONTROLLED),
        proposal_id="PROP-MC",
        timestamp="2026-06-01T00:01:00Z",
        model="claude-haiku-4-5-20251001",
    )
    assert proposal.producer.metadata == {"source_language": "en"}


def test_draft_extra_provenance_merges_client_kind() -> None:
    """A non-default rung's RoleProvenance.as_metadata() merges into producer.metadata."""
    intake = create_free_form_intake(
        intake_id="INTAKE-MC", original_text=_PROSE, submitted_at="2026-06-01T00:00:00Z"
    )
    extra = {"client_kind": "recorded", "prompt_version": _DRAFTING_PROMPT_VERSION}
    proposal = draft_controlled_rewrite_with_llm(
        intake=intake,
        client=RecordedLlmClient(_CONTROLLED),
        proposal_id="PROP-MC",
        timestamp="2026-06-01T00:01:00Z",
        model=None,
        extra_provenance=extra,
    )
    assert proposal.producer.metadata["source_language"] == "en"
    assert proposal.producer.metadata["client_kind"] == "recorded"
    assert proposal.producer.metadata["prompt_version"] == _DRAFTING_PROMPT_VERSION


# ---------------------------------------------------------------------------
# Positive recorded-transport round-trips through the factory
# ---------------------------------------------------------------------------


def test_recorded_decomposition_factory_round_trip(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A valid DecompositionResult fixture → RecordedDecompositionClient → same IR on replay."""
    _no_role_env(monkeypatch)
    ir = _parse_ir()
    result = DecompositionResult(
        requirement=ir,
        candidate_id="candidate-mc",
        source_text_hash=sha256_text(_FIXTURE_REQUIREMENT.read_text()),
        provenance={"source": "test_fixture", "model": "claude-haiku-4-5-20251001"},
    )
    fixture_path = tmp_path / "decomp.json"
    fixture_path.write_text(result.model_dump_json())

    built = build_client_for_role(Role.decomposition, None, fixture=fixture_path)
    assert isinstance(built.client, RecordedDecompositionClient)
    replayed = built.client.decompose_controlled_to_ir(
        _FIXTURE_REQUIREMENT.read_text(), requirement_id="R-MC", title="model-config test"
    )
    assert replayed.candidate_id == "candidate-mc"
    assert replayed.provenance["replay_marker"] == "recorded_fixture"
    assert replayed.provenance["model"] == "claude-haiku-4-5-20251001"


def test_recorded_audit_factory_round_trip(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A valid RecordedAuditFixture → RecordedAuditClient → verdict on replay."""
    _no_role_env(monkeypatch)
    controlled = "some controlled text"
    fixture = RecordedAuditFixture(
        verdict=AuditVerdict(covers_all_clauses=True, invented_premises=[], verdict="passed"),
        expected_controlled_text_hash=sha256_text(controlled),
    )
    fixture_path = tmp_path / "audit.json"
    fixture_path.write_text(fixture.model_dump_json())

    built = build_client_for_role(Role.audit, None, fixture=fixture_path)
    assert isinstance(built.client, RecordedAuditClient)
    verdict = built.client.audit_decomposition(controlled, ir_summary="summary")
    assert verdict.verdict == "passed"


# ---------------------------------------------------------------------------
# Config-file + env-var loading
# ---------------------------------------------------------------------------


def test_load_model_config_via_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _no_role_env(monkeypatch)
    cfg_path = _write_config(tmp_path, {"drafting": {"client": "anthropic", "model": "env-file-model"}})
    monkeypatch.setenv(CONFIG_PATH_ENV, str(cfg_path))
    cfg = load_model_config(None)
    assert cfg.drafting is not None
    built = build_client_for_role(Role.drafting, cfg)
    assert built.provenance.resolved_model == "env-file-model"
    assert built.provenance.source == "config-file"


def test_load_model_config_none_returns_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    _no_role_env(monkeypatch)
    cfg = load_model_config(None)
    assert isinstance(cfg, ModelConfig)
    assert cfg.drafting is None
    # An empty config → every role falls through to the pinned default.
    built = build_client_for_role(Role.impact, cfg)
    assert built.provenance.is_default is True


def test_cli_spec_parses_in_config(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """A cli spec in the config file parses (tier/model_env/timeout) into a CliLlmClient."""
    from nlreq.cli_llm_client import CliLlmClient

    _no_role_env(monkeypatch)
    cfg_path = tmp_path / "cli.toml"
    cfg_path.write_text(
        "[impact]\n"
        "client = 'cli'\n"
        "wrapper = 'run-gpt'\n"
        "tier = 'lite'\n"
        "timeout_s = 90.0\n"
        "[impact.model_env]\n"
        "GPT_LITE_MODEL = 'gpt-4o-mini'\n"
    )
    cfg = load_model_config(cfg_path)
    assert cfg.impact is not None
    built = build_client_for_role(Role.impact, cfg)
    assert isinstance(built.client, CliLlmClient)
    # The parsed spec fields are carried into the client (construction does not run the wrapper).
    assert built.client._wrapper == "run-gpt"
    assert built.client._tier == "lite"
    assert built.client._model_env == {"GPT_LITE_MODEL": "gpt-4o-mini"}
    assert built.client._timeout_s == 90.0


# ---------------------------------------------------------------------------
# CLI integration (CI-safe: refusals + recorded path, never a live API call)
# ---------------------------------------------------------------------------


def test_cli_intake_draft_cli_wrapper_not_found_exit_2(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A cli drafting config whose wrapper is absent refuses at run time (exit 2).

    The factory constructs the CliLlmClient; the drafting call then fails to resolve the
    wrapper on PATH → CliTransportError → exit 2 (no API fallback, no accepted draft).
    Uses a deliberately-absent wrapper name so the refusal is deterministic on any machine.
    """
    _no_role_env(monkeypatch)
    cfg_path = tmp_path / "cli-draft.toml"
    cfg_path.write_text("[drafting]\nclient = 'cli'\nwrapper = 'nlreq-nonexistent-wrapper-xyz'\n")
    prose = tmp_path / "prose.txt"
    prose.write_text(_PROSE)
    out = tmp_path / "proposal.json"

    exit_code = main([
        "intake-draft", str(prose),
        "--method", "llm",
        "--model-config", str(cfg_path),
        "--intake-id", "INTAKE-CLI",
        "--proposal-id", "PROP-CLI",
        "--out", str(out),
    ])
    assert exit_code == 2


def test_cli_intake_draft_env_cli_wrapper_not_found_exit_2(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """NLREQ_DRAFTING_CLIENT=cli with an absent wrapper refuses at the CLI (exit 2)."""
    _no_role_env(monkeypatch)
    monkeypatch.setenv("NLREQ_DRAFTING_CLIENT", "cli")
    monkeypatch.setenv("NLREQ_DRAFTING_WRAPPER", "nlreq-nonexistent-wrapper-xyz")
    prose = tmp_path / "prose.txt"
    prose.write_text(_PROSE)
    out = tmp_path / "proposal.json"

    exit_code = main([
        "intake-draft", str(prose),
        "--method", "llm",
        "--intake-id", "INTAKE-CLI",
        "--proposal-id", "PROP-CLI",
        "--out", str(out),
    ])
    assert exit_code == 2


def test_cli_intake_draft_fixture_records_client_kind(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The recorded drafting path (--fixture) now records client_kind=recorded in provenance.

    The existing source_language assertion still holds (test_multilingual_intake); this
    confirms the per-role client_kind provenance the scope requires is stamped for the
    recorded transport.
    """
    _no_role_env(monkeypatch)
    prose = tmp_path / "prose.txt"
    prose.write_text(_PROSE)
    fixture = tmp_path / "fixture.nlreq3"
    fixture.write_text(_CONTROLLED)
    out = tmp_path / "proposal.json"

    exit_code = main([
        "intake-draft", str(prose),
        "--method", "llm",
        "--fixture", str(fixture),
        "--intake-id", "INTAKE-CLI",
        "--proposal-id", "PROP-CLI",
        "--out", str(out),
    ])
    assert exit_code == 0
    proposal = json.loads(out.read_text())
    assert proposal["producer"]["metadata"]["source_language"] == "en"
    assert proposal["producer"]["metadata"]["client_kind"] == "recorded"
    assert proposal["producer"]["metadata"]["prompt_version"] == _DRAFTING_PROMPT_VERSION


def test_live_scheme_forces_anthropic_ignoring_cli_config(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """``live`` is a top-rung FORCE-ANTHROPIC override: it never silently resolves to ``cli``/
    ``recorded`` via env/config (a transport different from the requested one is a provenance
    hazard, ADR 0202). With a ``[decomposition] client='cli'`` config whose wrapper is absent,
    ``live`` MUST ignore the cli selection and build an Anthropic decomposition client instead."""
    from nlreq.cli import _resolve_client_scheme

    _no_role_env(monkeypatch)
    cfg_path = tmp_path / "cli-decomp.toml"
    cfg_path.write_text(
        "[decomposition]\nclient = 'cli'\nwrapper = 'nlreq-nonexistent-wrapper-xyz'\n"
    )
    cfg = load_model_config(cfg_path)

    built = _resolve_client_scheme("live", Role.decomposition, cfg)
    # `live` forced anthropic: the cli config (absent wrapper and all) was IGNORED.
    assert built.provenance.client_kind is ClientKind.anthropic
    assert isinstance(built.client, AnthropicDecompositionClient)
    # It is NOT a CliLlmClient — the cli transport was never selected despite the config.
    assert not hasattr(built.client, "_wrapper")
    # The absent wrapper is irrelevant because the cli rung was skipped entirely.
    assert built.provenance.wrapper is None


def test_live_scheme_no_config_is_default_anthropic_byte_stable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``live`` with no role config lands on the pinned anthropic default with ``is_default=True``,
    so NO ``client_kind`` is stamped — byte-identical to the pre-force-anthropic ``live`` path
    (the no-config ``live`` ensemble never recorded ``client_kind`` before, and still must not)."""
    from nlreq.cli import _resolve_client_scheme

    _no_role_env(monkeypatch)
    built = _resolve_client_scheme("live", Role.decomposition, ModelConfig())
    assert built.provenance.client_kind is ClientKind.anthropic
    assert isinstance(built.client, AnthropicDecompositionClient)
    assert built.provenance.is_default is True
    # is_default → as_metadata() is empty → no client_kind stamped (byte-stability).
    assert built.provenance.as_metadata() == {}


def test_live_scheme_honors_configured_anthropic_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``live`` still honors a configured anthropic *model* (env ``NLREQ_<ROLE>_MODEL`` when the
    role's env client is anthropic) — forcing the KIND to anthropic does not discard a
    configured anthropic model id."""
    from nlreq.cli import _resolve_client_scheme

    _no_role_env(monkeypatch)
    monkeypatch.setenv("NLREQ_DECOMPOSITION_CLIENT", "anthropic")
    monkeypatch.setenv("NLREQ_DECOMPOSITION_MODEL", "claude-sonnet-4-6")
    built = _resolve_client_scheme("live", Role.decomposition, ModelConfig())
    assert built.provenance.client_kind is ClientKind.anthropic
    assert isinstance(built.client, AnthropicDecompositionClient)
    assert built.provenance.resolved_model == "claude-sonnet-4-6"
    # A configured (non-default) anthropic model IS recorded as client_kind=anthropic.
    assert built.provenance.as_metadata()["client_kind"] == "anthropic"


def test_live_scheme_skips_cli_env_without_wrapper(monkeypatch: pytest.MonkeyPatch) -> None:
    """The bare ``live`` scheme (force_anthropic) skips a ``cli`` env selection WITHOUT validating
    its required companion — ``NLREQ_DECOMPOSITION_CLIENT=cli`` with no ``NLREQ_DECOMPOSITION_WRAPPER``
    must NOT raise (iter-3 MEDIUM fix). Previously ``_env_spec_for_role`` eagerly validated the
    wrapper before ``_resolve``'s force_anthropic skip could ignore the cli rung, so an incomplete
    cli env selection surfaced as ``ModelConfigError`` instead of forcing anthropic. ``live`` forces
    anthropic: it honors a configured anthropic model, else the pinned default (here the default, so
    no ``client_kind`` is stamped — byte-identical to the no-config ``live`` path)."""
    from nlreq.cli import _resolve_client_scheme

    _no_role_env(monkeypatch)
    monkeypatch.setenv("NLREQ_DECOMPOSITION_CLIENT", "cli")
    # No NLREQ_DECOMPOSITION_WRAPPER — an incomplete cli env rung `live` must ignore, not validate.
    built = _resolve_client_scheme("live", Role.decomposition, ModelConfig())
    assert built.provenance.client_kind is ClientKind.anthropic
    assert isinstance(built.client, AnthropicDecompositionClient)
    # The cli rung was skipped entirely (no transport switch); it lands on the pinned default.
    assert built.provenance.wrapper is None
    assert built.provenance.is_default is True
    assert built.provenance.as_metadata() == {}


def test_live_scheme_skips_recorded_env_without_fixture(monkeypatch: pytest.MonkeyPatch) -> None:
    """The bare ``live`` scheme skips a ``recorded`` env selection WITHOUT validating its required
    companion — ``NLREQ_DECOMPOSITION_CLIENT=recorded`` with no ``NLREQ_DECOMPOSITION_FIXTURE`` must
    NOT raise (iter-3 MEDIUM fix). Same no-validation skip as the cli branch: ``live`` forces
    anthropic and ignores the incomplete recorded rung, landing on the pinned default."""
    from nlreq.cli import _resolve_client_scheme

    _no_role_env(monkeypatch)
    monkeypatch.setenv("NLREQ_DECOMPOSITION_CLIENT", "recorded")
    # No NLREQ_DECOMPOSITION_FIXTURE — an incomplete recorded env rung `live` must ignore.
    built = _resolve_client_scheme("live", Role.decomposition, ModelConfig())
    assert built.provenance.client_kind is ClientKind.anthropic
    assert isinstance(built.client, AnthropicDecompositionClient)
    assert built.provenance.is_default is True
    assert built.provenance.as_metadata() == {}


def test_cli_semantic_translate_unknown_spec_still_exit_2(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Regression: the unknown-spec refusal (exit 2) is preserved through the factory wiring."""
    _no_role_env(monkeypatch)
    req = tmp_path / "req.nlreq"
    req.write_text(_CONTROLLED)
    exit_code = main([
        "semantic-translate", str(req),
        "--requirement-id", "R-CLI",
        "--title", "t",
        "--ensemble-client", "unknown-format-xyz",
    ])
    assert exit_code == 2


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _write_config(tmp_path: Path, roles: dict[str, dict[str, object]]) -> Path:
    """Write a minimal nlreq-models.toml with the given role sections; return its path."""
    lines: list[str] = []
    for role_name, spec in roles.items():
        lines.append(f"[{role_name}]")
        for key, value in spec.items():
            if isinstance(value, str):
                lines.append(f"{key} = {json.dumps(value)}")
            elif isinstance(value, bool):
                lines.append(f"{key} = {'true' if value else 'false'}")
            else:
                lines.append(f"{key} = {value}")
        lines.append("")
    path = tmp_path / "nlreq-models.toml"
    path.write_text("\n".join(lines))
    return path
