"""Per-role LLM model configuration and the single client-construction factory.

Work Item 1 of the nlreq scope *Per-Role Model Config + CLI-Backed Cross-Provider
LLM Adapter*. nlreq's five LLM roles — drafting, decomposition, impact, extraction,
audit — historically each reached a pinned module constant (``_DEFAULT_MODEL`` &
co.) with no config surface and no per-role selection object. This module
introduces that object and a four-rung resolution ladder (highest wins):

    per-call override  →  NLREQ_<ROLE>_* env vars  →  nlreq-models.toml
                         (``--model-config`` / ``NLREQ_MODEL_CONFIG``)  →  pinned constants

Design invariants (see ADR 0202 for the full rationale):

* **Zero behaviour change when nothing is configured** — the lowest rung reproduces
  the exact ``Anthropic*Client(model=<pinned default>)`` construction and the exact
  provenance bytes the CLI emitted before this module existed. New provenance fields
  (``client_kind`` / ``prompt_version`` / ``wrapper``) are recorded ONLY when a
  non-default rung resolves, so default-path artifacts stay byte-identical. This is
  acceptance criterion #1 of the scope.

* **The shipped zero-config default transport is Anthropic** — the Messages API
  response carries the exact model snapshot id, the highest-precision provenance,
  which is what an attestation tool's default should be. Operators make ``cli`` their
  *effective* default via machine-level config/env (one-time, wins over the file
  default — the same philosophy as the operator ``models.env`` conditional
  assignment). **Transport auto-detection with fallback is PROHIBITED**: a transport
  silently different from the configured one is the same provenance hazard as a
  silent model fallback.

* **Unknown role/kind → structured refusal, never a faked client** —
  ``ModelConfigError`` carries an actionable message; the CLI surfaces it as exit 2.
  Selecting the ``cli`` kind with a missing wrapper, or a malformed recorded fixture, is a
  structured refusal, not a silently-different (API) transport.

* **Single construction point** — ``build_client_for_role`` is the one place the CLI
  commands construct an LLM/decomposition/audit client. It returns a ``BuiltClient``
  pairing the client with a ``RoleProvenance`` record (client kind, resolved model,
  prompt version, wrapper, and the ladder rung that resolved) so callers can stamp
  per-role provenance into the package/proposal artifacts.
"""
from __future__ import annotations

import json
import os
import tomllib
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field

# Re-exported so callers import the error from the config module (single source).
__all__ = [
    "Role",
    "ClientKind",
    "ModelConfig",
    "RoleProvenance",
    "BuiltClient",
    "CliOverride",
    "ModelConfigError",
    "DEFAULT_CONFIG_FILENAME",
    "CONFIG_PATH_ENV",
    "PROVIDER_FAMILY_BY_WRAPPER",
    "PROVIDER_FAMILY_BY_PROVIDER",
    "provider_family_for",
    "load_model_config",
    "build_client_for_role",
]


# ---------------------------------------------------------------------------
# Provider-family metadata (three-zone scope §3)
# ---------------------------------------------------------------------------
#
# The per-role scope records the *provider* (wrapper) and resolved model id and frames diversity
# as "two providers / avoid same-family correlated bias", but it does NOT define a machine-readable
# provider-FAMILY grouping or a "two distinct families" predicate — and two distinct *providers*
# can still be the same family (e.g. two wrappers both resolving to Anthropic models, or two
# OpenRouter-routed models). The three-zone scope OWNS this contract (§3): a family tag coarser
# than the wrapper, plus a "≥2 distinct families" predicate the partition-ensemble and
# machine-agreement diversity gates need. ``provider_family_for`` is the single resolver both
# gates call.
#
# The family is derived from the OPERATOR WRAPPER name (a known finite set — run-claude / run-gpt /
# run-gemini / run-oss / run-oss-local, per ``cli_llm_client``) so it is known at CONSTRUCTION time
# (the diversity gate runs before any call), with a sidecar-``provider`` fallback for a wrapper not
# in the table. The anthropic kind is always ``"anthropic"``; the recorded kind has no live model.

PROVIDER_FAMILY_BY_WRAPPER: dict[str, str] = {
    "run-claude": "anthropic",
    "run-gpt": "openai",
    "run-gemini": "google",
    "run-oss": "open-source",
    "run-oss-local": "open-source",
}

PROVIDER_FAMILY_BY_PROVIDER: dict[str, str] = {
    "anthropic": "anthropic",
    "openai": "openai",
    "google": "google",
    "gemini": "google",
    "meta": "meta",
    "mistral": "mistral",
    "ollama": "open-source",
    "openrouter": "open-source",
    "open-source": "open-source",
    "together": "open-source",
}


def provider_family_for(
    *,
    client_kind: "ClientKind",
    wrapper: str | None = None,
    provider: str | None = None,
) -> str | None:
    """Resolve the provider FAMILY of a client — coarser than the wrapper (three-zone §3).

    The diversity gate (partition ensemble / machine agreement) requires ≥2 distinct provider
    *families*, not merely ≥2 distinct providers: two wrappers can resolve to the same family
    (e.g. two OpenRouter-routed models, or two Anthropic-resolving wrappers) and so share
    correlated training bias. The family is derived as:

      * ``anthropic`` kind  → ``"anthropic"`` (deterministic; the SDK transport is Anthropic-only).
      * ``cli`` kind        → the wrapper-basename family from ``PROVIDER_FAMILY_BY_WRAPPER``
                              (run-claude→anthropic, run-gpt→openai, …), falling back to the
                              sidecar ``provider`` family when the wrapper is not in the table.
      * ``recorded`` kind   → ``None`` (no live model; a recorded fixture carries no family).

    Returns ``None`` when the family cannot be resolved (an unknown wrapper with no provider),
    which the diversity gate treats as "cannot satisfy distinct-family" rather than guessing —
    a same-family/unknown ensemble routes to the human queue, never a silent pin (AC7).
    """
    if client_kind is ClientKind.anthropic:
        return "anthropic"
    if client_kind is ClientKind.cli:
        if wrapper:
            base = os.path.basename(wrapper)
            family = PROVIDER_FAMILY_BY_WRAPPER.get(base)
            if family is not None:
                return family
        if provider:
            return PROVIDER_FAMILY_BY_PROVIDER.get(str(provider).strip().lower())
        return None
    # recorded: no live model, no family.
    return None


class ModelConfigError(ValueError):
    """Structured error for an unresolvable or invalid per-role model configuration.

    Raised for unknown roles/kinds, a config file that selects the ``cli``
    transport without a wrapper, missing required fields for a kind, or a recorded fixture that
    cannot be loaded. The CLI turns this into exit 2 with the message — it never
    degrades to a silently-different client.
    """


class Role(str, Enum):
    """The six LLM roles nlreq configures independently.

    ``drafting`` / ``impact`` / ``extraction`` / ``partition`` share the ``LlmClient`` type
    (four methods on one protocol) but are distinct roles: a project may want a stronger model
    for drafting and a cheaper model for impact estimation. ``partition`` (three-zone scope §3/§4)
    is the spec-partitioning proposal role (document segment → candidate rules); it is named
    ``partition`` to avoid colliding with the existing ``decomposition`` (controlled→IR) and
    ``extraction`` (Specula) roles. ``decomposition`` and ``audit`` have their own protocol/
    client families.
    """

    drafting = "drafting"
    decomposition = "decomposition"
    impact = "impact"
    extraction = "extraction"
    audit = "audit"
    partition = "partition"


class ClientKind(str, Enum):
    """How a role's client is realized.

    ``anthropic`` — in-process Anthropic SDK call (the precision transport; the
    response carries the exact model snapshot id). ``cli`` — subprocess call to an
    operator wrapper executable for cross-provider diversity (Work Item 2/3 wires the
    transport for all six roles). ``recorded`` — deterministic fixture replay for
    offline/CI use.
    """

    anthropic = "anthropic"
    cli = "cli"
    recorded = "recorded"


# The config-file name consulted when --model-config / NLREQ_MODEL_CONFIG is absent but
# a default-named file is wanted. Resolution never auto-creates or auto-discovers
# transport (that would violate the no-silent-fallback invariant); this constant only
# names the conventional file a user opts into via the env var.
DEFAULT_CONFIG_FILENAME = "nlreq-models.toml"
CONFIG_PATH_ENV = "NLREQ_MODEL_CONFIG"


# --- Per-role spec types (the shape of one role's entry in nlreq-models.toml / env) ---
#
# extra="forbid" on every spec: a typo in a config file (e.g. ``moodel =``) is a
# provenance hazard for an attestation tool, so it refuses rather than silently
# ignoring the misnamed key.


class _AnthropicSpec(BaseModel):
    """Anthropic SDK transport for a role: just the model id."""

    model_config = ConfigDict(extra="forbid")

    client: Literal["anthropic"]
    model: str


class _CliSpec(BaseModel):
    """Subprocess-wrapper transport for a role (cross-provider diversity).

    ``wrapper`` is the executable name/path (e.g. ``run-gpt``); ``tier`` is the
    optional 1..5 capability-ladder indirection. ``model_env`` exports explicit model ids
    that win over the wrapper's ``models.env`` defaults (conditional-assignment form
    → process env wins), so the resolved model is chosen by nlreq, not by the file
    default at call time — provenance always records the resolved id, never the tier.
    The pure-completion profile (no tools / no cwd context / no silent fallback) is
    enforced per-call by ``CliLlmClient`` (Work Item 2); ``timeout_s`` bounds the tail.
    """

    model_config = ConfigDict(extra="forbid")

    client: Literal["cli"]
    wrapper: str
    tier: str | None = None
    model_env: dict[str, str] = Field(default_factory=dict)
    timeout_s: float = 120.0


class _RecordedSpec(BaseModel):
    """Deterministic fixture-replay transport for a role: the fixture file path."""

    model_config = ConfigDict(extra="forbid")

    client: Literal["recorded"]
    fixture: str


# Discriminated union on ``client`` so pydantic validates exactly one spec shape per
# role section and rejects ambiguous/mixed keys.
RoleSpec = Annotated[
    Union[_AnthropicSpec, _CliSpec, _RecordedSpec],
    Field(discriminator="client"),
]


class ModelConfig(BaseModel):
    """Resolved per-role model configuration loaded from ``nlreq-models.toml``.

    Every role is optional; an absent role falls through the ladder to the pinned
    constants. ``extra="forbid"`` so a config file cannot quietly introduce an
    unknown role name (e.g. ``[draft]`` instead of ``[drafting]``).
    """

    model_config = ConfigDict(extra="forbid")

    drafting: RoleSpec | None = None
    decomposition: RoleSpec | None = None
    impact: RoleSpec | None = None
    extraction: RoleSpec | None = None
    audit: RoleSpec | None = None
    partition: RoleSpec | None = None


@dataclass(frozen=True)
class RoleProvenance:
    """Per-role provenance the factory resolves alongside the client.

    Callers merge ``as_metadata()`` into the artifact's provenance/metadata map.
    It is empty for the default path so default-path artifacts stay byte-identical
    to the pre-config CLI (acceptance #1). ``resolved_model`` is only meaningful for
    the ``cli`` transport (the sidecar-resolved id, distinct from any tier); for
    ``anthropic`` the model id is already recorded in the artifact's ``model`` field,
    so it is not duplicated here.
    """

    role: Role
    client_kind: ClientKind
    resolved_model: str | None
    prompt_version: str | None
    wrapper: str | None
    source: str
    is_default: bool
    # The provider FAMILY (three-zone scope §3), coarser than ``wrapper``. ``None`` for the
    # recorded kind (no live model) and for a ``cli`` wrapper whose family is unresolvable. Read
    # directly by the partition-ensemble and machine-agreement diversity gates; DELIBERATELY NOT
    # emitted by ``as_metadata()`` so default-path artifact bytes stay byte-identical (AC1) — the
    # family is a routing input, not stamped artifact provenance.
    provider_family: str | None = None

    def as_metadata(self) -> dict[str, str]:
        """Flat string→string map for artifact metadata; empty on the default path.

        Empty for the default path → default-path artifacts are byte-identical to the
        pre-config CLI. Non-default paths record ``client_kind`` plus
        ``prompt_version`` (when the role has a versioned prompt) and ``wrapper``
        (cli only). ``resolved_model`` is reserved for the cli transport (Work Item 2).
        """
        if self.is_default:
            return {}
        meta: dict[str, str] = {"client_kind": self.client_kind.value}
        if self.prompt_version is not None:
            meta["prompt_version"] = self.prompt_version
        if self.wrapper is not None:
            meta["wrapper"] = self.wrapper
        # resolved_model is emitted only for the cli transport: for anthropic the model id is
        # already recorded in the artifact's ``model`` field (duplicating it would be noise),
        # and for the cli transport the sidecar-resolved id is distinct from any tier and MUST
        # be recorded (Work Item 2). For recorded there is no live model id.
        if self.client_kind is ClientKind.cli and self.resolved_model is not None:
            meta["resolved_model"] = self.resolved_model
        return meta


@dataclass(frozen=True)
class BuiltClient:
    """A constructed client paired with its resolved per-role provenance."""

    client: object  # LlmClient | DecompositionClient | AuditClient implementer
    provenance: RoleProvenance


@dataclass(frozen=True)
class CliOverride:
    """Per-call override selecting the cli transport with a specific wrapper (rung 1).

    The ``cli:<wrapper>[:<tier-or-model>]`` ensemble/audit scheme parses into this. It bypasses the
    env/file/default rungs (a per-call scheme is the highest-rung override) and selects the cli
    kind with the given wrapper, an optional ``tier`` (1|2|3|4|5, passed as ``--tier``),
    and/or an optional ``expected_model`` (the exact resolved model id the sidecar MUST report).
    The factory then constructs a ``CliLlmClient`` for any of the six roles.

    **Explicit model vs tier.** The operator wrappers resolve a model from wrapper+tier-specific
    env vars (e.g. ``CLAUDE_TIER3_MODEL``) sourced from ``models.env`` in conditional-assignment
    form, so the per-call scheme CANNOT pin a model without wrapper-specific env-var knowledge —
    that pinning is the config/env ``model_env`` rung's job. The per-call ``expected_model`` is a
    *verification*: the fail-closed sidecar check refuses if the wrapper resolved a different
    model than the scheme required, so provenance records the sidecar-resolved id, never the tier
    (scope §4). This makes the per-call scheme assert exactly which model answered.
    """

    wrapper: str
    tier: str | None = None
    expected_model: str | None = None


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------


def _resolve_config_path(path: Path | None) -> Path | None:
    """Resolve the config-file path: explicit arg → NLREQ_MODEL_CONFIG → None.

    Never auto-discovers a transport config: a missing env var and no --model-config
    means "use the pinned defaults", not "search for nlreq-models.toml". This keeps
    the no-silent-fallback invariant — the operator opts into a config file
    explicitly.
    """
    if path is not None:
        return path
    env_path = os.environ.get(CONFIG_PATH_ENV, "").strip()
    if env_path:
        return Path(env_path)
    return None


def load_model_config(path: Path | None = None) -> ModelConfig:
    """Load the per-role model config from TOML; empty ``ModelConfig`` if none.

    Args:
        path: Explicit ``--model-config`` path. When None, falls back to
            ``NLREQ_MODEL_CONFIG``; when that is also unset, returns an empty config
            (every role falls through to the pinned constants).

    Raises:
        ModelConfigError: If the file is unreadable, unparseable TOML, or fails
            pydantic validation (unknown role, ambiguous kind, forbidden extra keys).
    """
    resolved = _resolve_config_path(path)
    if resolved is None:
        return ModelConfig()
    if not resolved.is_file():
        raise ModelConfigError(
            f"model config file not found: {resolved} (set via --model-config or {CONFIG_PATH_ENV})"
        )
    try:
        with resolved.open("rb") as handle:
            data = tomllib.load(handle)
    except tomllib.TOMLDecodeError as exc:
        raise ModelConfigError(f"model config {resolved} is not valid TOML: {exc}") from exc
    try:
        return ModelConfig.model_validate(data)
    except ValueError as exc:
        raise ModelConfigError(f"model config {resolved} is invalid: {exc}") from exc


# ---------------------------------------------------------------------------
# Resolution ladder
# ---------------------------------------------------------------------------


def _env_spec_for_role(role: Role, *, force_anthropic: bool = False) -> object | None:
    """Build a role spec from ``NLREQ_<ROLE>_*`` env vars, or None when unset.

    ``force_anthropic`` (the bare ``live`` scheme) SKIPS a ``cli``/``recorded`` env selection
    WITHOUT validating its required companion (``_WRAPPER``/``_FIXTURE``): an explicit ``live``
    forces the anthropic kind, so an incomplete cli/recorded env rung it would have ignored
    anyway must never raise — it returns None and the ladder honors a configured anthropic model
    or falls through to the default. A transport different from the requested one is a provenance
    hazard (ADR 0202), so the skip is total (no silent transport switch).

    ``NLREQ_DRAFTING_CLIENT`` selects the kind; the kind's required companions are
    ``NLREQ_DRAFTING_MODEL`` (anthropic), ``NLREQ_DRAFTING_WRAPPER`` [+ ``_TIER``]
    (cli), or ``NLREQ_DRAFTING_FIXTURE`` (recorded). A kind set without its required
    companion is a structured refusal, not a silent default. A model-only override
    (``NLREQ_<ROLE>_MODEL`` with ``NLREQ_<ROLE>_CLIENT`` unset) resolves as an
    anthropic spec, honoring the resolution ladder's documented env-rung model
    override (a bare model env is only meaningful for the anthropic kind — cli uses
    ``_MODEL_ENV``, recorded uses ``_FIXTURE`` — so it unambiguously selects anthropic).
    """
    prefix = f"NLREQ_{role.name.upper()}"
    client = os.environ.get(f"{prefix}_CLIENT", "").strip()
    if not client:
        # No kind selected explicitly. A model-only env override (NLREQ_<ROLE>_MODEL without
        # NLREQ_<ROLE>_CLIENT) resolves as an anthropic spec — the documented resolution ladder
        # (ADR 0202) honors a configured anthropic model when the client kind is unset, mirroring
        # the operator models.env conditional-assignment philosophy: an explicit per-role model
        # env wins over the pinned default without forcing the operator to also spell out
        # NLREQ_<ROLE>_CLIENT=anthropic. The model env var is only meaningful for the anthropic
        # kind (cli pinning uses NLREQ_<ROLE>_MODEL_ENV; recorded uses NLREQ_<ROLE>_FIXTURE), so
        # a bare model env unambiguously selects anthropic. None when no role env is set at all
        # (falls through to the config-file/default rungs → byte-identical default path).
        model = os.environ.get(f"{prefix}_MODEL", "").strip()
        if model:
            return _AnthropicSpec(client="anthropic", model=model)
        return None
    if client == ClientKind.anthropic.value:
        model = os.environ.get(f"{prefix}_MODEL", "").strip()
        if not model:
            raise ModelConfigError(
                f"{prefix}_CLIENT=anthropic requires {prefix}_MODEL to be set"
            )
        return _AnthropicSpec(client="anthropic", model=model)
    if client == ClientKind.cli.value:
        if force_anthropic:
            # Bare `live` forces the anthropic kind: a cli env selection is SKIPPED without
            # validating NLREQ_<ROLE>_WRAPPER, so an explicit live scheme never raises on an
            # incomplete cli env rung it would have ignored anyway (iter-3 MEDIUM fix). It forces
            # anthropic instead — no silent transport switch (ADR 0202).
            return None
        wrapper = os.environ.get(f"{prefix}_WRAPPER", "").strip()
        if not wrapper:
            raise ModelConfigError(
                f"{prefix}_CLIENT=cli requires {prefix}_WRAPPER to be set"
            )
        tier = os.environ.get(f"{prefix}_TIER", "").strip() or None
        model_env = _parse_model_env_env(f"{prefix}_MODEL_ENV")
        timeout_s = _parse_timeout_env(f"{prefix}_TIMEOUT_S")
        return _CliSpec(
            client="cli", wrapper=wrapper, tier=tier, model_env=model_env, timeout_s=timeout_s
        )
    if client == ClientKind.recorded.value:
        if force_anthropic:
            # Bare `live` forces the anthropic kind: a recorded env selection is SKIPPED without
            # validating NLREQ_<ROLE>_FIXTURE — same no-validation skip as the cli branch above
            # (iter-3 MEDIUM fix). It forces anthropic instead; no silent transport switch.
            return None
        fixture = os.environ.get(f"{prefix}_FIXTURE", "").strip()
        if not fixture:
            raise ModelConfigError(
                f"{prefix}_CLIENT=recorded requires {prefix}_FIXTURE to be set"
            )
        return _RecordedSpec(client="recorded", fixture=fixture)
    raise ModelConfigError(
        f"unknown {prefix}_CLIENT={client!r} (use 'anthropic', 'cli', or 'recorded')"
    )


def _parse_model_env_env(var: str) -> dict[str, str]:
    """Parse ``NLREQ_<ROLE>_MODEL_ENV`` (a JSON object of env-var → model-id) into a dict.

    This is the env-rung way to pin an explicit model id that wins over the wrapper's
    ``models.env`` defaults (conditional-assignment form → process env wins), so the
    resolved model is chosen by nlreq, not by the file default at call time. Provenance
    always records the sidecar-resolved id, never the tier (scope §4). A non-JSON or
    non-string→string value is a structured refusal, not a silent ignore.
    """
    raw = os.environ.get(var, "").strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ModelConfigError(
            f"{var} is not valid JSON (expected an object of env-var -> model-id): {exc}"
        ) from exc
    if not isinstance(parsed, dict) or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in parsed.items()
    ):
        raise ModelConfigError(
            f"{var} must be a JSON object of string -> string (env-var -> model-id)"
        )
    return dict(parsed)


def _parse_timeout_env(var: str) -> float:
    """Parse ``NLREQ_<ROLE>_TIMEOUT_S`` as a positive float; default 120s when unset."""
    raw = os.environ.get(var, "").strip()
    if not raw:
        return 120.0
    try:
        value = float(raw)
    except ValueError as exc:
        raise ModelConfigError(f"{var} must be a positive number of seconds: {exc}") from exc
    if value <= 0:
        raise ModelConfigError(f"{var} must be a positive number of seconds, got {value}")
    return value


def _default_model_for_role(role: Role) -> str:
    """The pinned module constant for a role — the lowest ladder rung.

    Imported lazily so this module is a clean leaf: it never triggers SDK or heavy
    imports at module load, and a unit test can import ``model_config`` without
    pulling the full client stack.
    """
    if role is Role.decomposition:
        from .decomposition_client import _DEFAULT_DECOMPOSITION_MODEL

        return _DEFAULT_DECOMPOSITION_MODEL
    if role is Role.audit:
        from .audit_client import _DEFAULT_AUDIT_MODEL

        return _DEFAULT_AUDIT_MODEL
    # drafting / impact / extraction / partition share the LlmClient default.
    from .llm_client import _DEFAULT_MODEL

    return _DEFAULT_MODEL


def _prompt_version_for_role(role: Role) -> str | None:
    """The version stamp of the role's prompt template, or None when unversioned.

    Each role's prompt carries a module-level version stamp (Work Item 2 lifted the
    drafting/impact/extraction prompts into shared versioned templates alongside the
    already-versioned decomposition/audit prompts). The stamp is stable across the lift
    because the prompt text — and therefore ``prompt_hash`` — is unchanged.
    """
    if role is Role.decomposition:
        from .decomposition_client import _DECOMPOSITION_PROMPT_VERSION

        return _DECOMPOSITION_PROMPT_VERSION
    if role is Role.audit:
        from .audit_client import _AUDIT_PROMPT_VERSION

        return _AUDIT_PROMPT_VERSION
    if role is Role.drafting:
        from .llm_client import _DRAFTING_PROMPT_VERSION

        return _DRAFTING_PROMPT_VERSION
    if role is Role.impact:
        from .llm_client import _IMPACT_PROMPT_VERSION

        return _IMPACT_PROMPT_VERSION
    if role is Role.extraction:
        from .llm_client import _EXTRACTION_PROMPT_VERSION

        return _EXTRACTION_PROMPT_VERSION
    if role is Role.partition:
        from .llm_client import _PARTITION_PROMPT_VERSION

        return _PARTITION_PROMPT_VERSION
    return None


@dataclass(frozen=True)
class _Resolved:
    """Internal: the resolved kind + kind-specific fields + the ladder rung that won."""

    kind: ClientKind
    model: str | None = None  # anthropic
    wrapper: str | None = None  # cli
    tier: str | None = None  # cli
    expected_model: str | None = None  # cli (per-call resolved-model verification)
    model_env: dict[str, str] | None = None  # cli
    timeout_s: float = 120.0  # cli
    fixture_path: Path | None = None  # recorded
    source: str = "default"
    is_default: bool = True


def _from_spec(spec: object, *, source: str, is_default: bool) -> _Resolved:
    """Translate a validated role spec into the internal ``_Resolved`` form."""
    if isinstance(spec, _AnthropicSpec):
        return _Resolved(
            ClientKind.anthropic, model=spec.model, source=source, is_default=is_default
        )
    if isinstance(spec, _CliSpec):
        return _Resolved(
            ClientKind.cli,
            wrapper=spec.wrapper,
            tier=spec.tier,
            model_env=dict(spec.model_env),
            timeout_s=spec.timeout_s,
            source=source,
            is_default=is_default,
        )
    if isinstance(spec, _RecordedSpec):
        return _Resolved(
            ClientKind.recorded,
            fixture_path=Path(spec.fixture),
            source=source,
            is_default=is_default,
        )
    raise ModelConfigError(f"unknown role spec kind: {spec!r}")


def _resolve(
    role: Role,
    config: ModelConfig | None,
    *,
    model_override: str | None,
    fixture_override: Path | None,
    cli_override: "CliOverride | None",
    force_anthropic: bool = False,
) -> _Resolved:
    """Apply the four-rung ladder (override → env → config file → pinned default).

    When ``force_anthropic`` is set (the bare ``live`` scheme, ADR 0202), the KIND is forced
    to anthropic: a ``cli``/``recorded`` per-call override AND a ``cli``/``recorded``
    env/config selection are SKIPPED, so an explicit ``live`` never silently resolves to a
    different transport — the same no-silent-fallback invariant that forbids transport
    auto-detection. A configured anthropic *model* is still honored (env
    ``NLREQ_<ROLE>_MODEL`` when ``NLREQ_<ROLE>_CLIENT`` is unset/anthropic, or a config
    ``[role] client='anthropic'`` section); otherwise the pinned default model is used with
    ``is_default=True``, so a bare ``live`` that lands on the default model stamps no
    ``client_kind`` (byte-identical to the no-config ``live`` path). ``live:<model>`` reaches
    this via ``model_override`` (already anthropic) and needs no forcing.
    """
    # 1. Per-call overrides (highest). The three override forms are mutually exclusive in
    #    practice (a call passes either --model, --fixture, or a cli: scheme); each selects
    #    its kind and short-circuits the ladder. ``force_anthropic`` (bare ``live``) skips the
    #    cli/recorded overrides — it forces the anthropic kind, never a silent transport switch.
    if cli_override is not None and not force_anthropic:
        return _Resolved(
            ClientKind.cli,
            wrapper=cli_override.wrapper,
            tier=cli_override.tier,
            expected_model=cli_override.expected_model,
            source="override",
            is_default=False,
        )
    if fixture_override is not None and not force_anthropic:
        return _Resolved(
            ClientKind.recorded,
            fixture_path=fixture_override,
            source="override",
            is_default=False,
        )
    if model_override is not None:
        return _Resolved(
            ClientKind.anthropic,
            model=model_override,
            source="override",
            is_default=False,
        )
    # 2. Environment variables.
    # ``force_anthropic`` (bare ``live``) skips cli/recorded env selections WITHOUT validating
    # their required companions — done inside ``_env_spec_for_role`` (returns None for cli/
    # recorded), so an incomplete cli/recorded env rung never raises here. An explicit ``live``
    # forces the anthropic kind: it honors a configured anthropic model or falls through; a
    # transport different from the requested one is a provenance hazard (ADR 0202).
    env_spec = _env_spec_for_role(role, force_anthropic=force_anthropic)
    if env_spec is not None:
        return _from_spec(env_spec, source="env", is_default=False)
    # 3. Config file.
    if config is not None:
        file_spec = getattr(config, role.value, None)
        if file_spec is not None:
            if force_anthropic and not isinstance(file_spec, _AnthropicSpec):
                # Bare `live` ignores a cli/recorded config selection — it forces anthropic.
                pass
            else:
                return _from_spec(file_spec, source="config-file", is_default=False)
    # 4. Pinned constants (lowest) — zero behaviour change when nothing is configured.
    return _Resolved(
        ClientKind.anthropic,
        model=_default_model_for_role(role),
        source="default",
        is_default=True,
    )


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


def _llm_roles() -> frozenset[Role]:
    """Roles backed by the ``LlmClient`` protocol (drafting/impact/extraction/partition).

    ``partition`` (three-zone scope) is an LlmClient role: it proposes plain-language candidate
    requirements from a segment via ``propose_candidate_rules``, the same text-in/text-out
    protocol the other three share.
    """
    return frozenset({Role.drafting, Role.impact, Role.extraction, Role.partition})


def _construct_anthropic(role: Role, resolved: _Resolved, provenance: RoleProvenance) -> object:
    """Build the Anthropic SDK client for a role.

    For decomposition the client emits ``client_kind`` into its runtime provenance
    dict — but ONLY on a non-default rung (``client_kind=None`` on the default path
    keeps ``AnthropicDecompositionClient``'s output byte-identical to the pre-config
    CLI). Audit's ``AuditVerdict`` carries full CLI-transport provenance
    (``client_kind`` / ``provider`` / ``route`` / ``wrapper`` / ``wrapper_hash`` /
    ``cli_version``) when the CLI audit transport set them (ADR 0205); the anthropic/
    recorded audit paths leave those fields None (byte-identical to pre-config).
    ``LlmClient`` carries no runtime provenance — the caller merges
    ``RoleProvenance.as_metadata()`` (and, for the cli transport,
    ``CliLlmClient.last_call_provenance()``) into the proposal.
    """
    model = resolved.model or _default_model_for_role(role)
    # client_kind is emitted into the artifact only when a non-default rung resolved,
    # so the default path stays byte-identical (acceptance #1).
    emitted_kind = None if provenance.is_default else provenance.client_kind.value
    if role in _llm_roles():
        from .llm_client import AnthropicLlmClient

        return AnthropicLlmClient(model=model)
    if role is Role.decomposition:
        from .decomposition_client import AnthropicDecompositionClient

        return AnthropicDecompositionClient(model=model, client_kind=emitted_kind)
    if role is Role.audit:
        from .audit_client import AnthropicAuditClient

        return AnthropicAuditClient(model=model)
    raise ModelConfigError(f"no anthropic constructor for role {role!r}")


def _construct_recorded(role: Role, resolved: _Resolved) -> object:
    """Build the deterministic fixture-replay client for a role.

    The recorded kind is the offline/CI transport. Each role's fixture has a
    different shape (drafting = raw controlled text; decomposition = a
    ``DecompositionResult`` JSON; audit = a hash-bound ``RecordedAuditFixture``
    JSON), so the loader is role-specific. The construction mirrors the CLI's prior
    inline fixture handling exactly so replay bytes are unchanged.
    """
    path = resolved.fixture_path
    if path is None or not path.is_file():
        raise ModelConfigError(
            f"recorded fixture for role {role.value} not found: {path!r}"
        )
    text = path.read_text(encoding="utf-8")
    if role in _llm_roles():
        from .llm_client import RecordedLlmClient

        # Drafting replays the controlled-text fixture verbatim. (impact/extraction
        # recorded replay is CLI-managed via --spec-fixture and is not routed through
        # this generic factory; their live-client exposure is via --llm-client.)
        return RecordedLlmClient(text)
    if role is Role.decomposition:
        from .decomposition_client import DecompositionResult, RecordedDecompositionClient

        try:
            fixture_result = DecompositionResult.model_validate_json(text)
        except ValueError as exc:
            raise ModelConfigError(
                f"recorded decomposition fixture {path} is not a valid DecompositionResult: {exc}"
            ) from exc
        return RecordedDecompositionClient(
            fixture=fixture_result.requirement,
            candidate_id=fixture_result.candidate_id,
            approval=fixture_result.approval,
            is_audited=fixture_result.is_audited,
            audit_verdict=fixture_result.audit_verdict,
            model_id=fixture_result.model_id,
            prompt_hash=fixture_result.prompt_hash,
            fixture_provenance=fixture_result.provenance,
            source_spans=fixture_result.source_spans,
            expected_source_text_hash=fixture_result.source_text_hash,
        )
    if role is Role.audit:
        from .audit_client import RecordedAuditFixture

        try:
            audit_fixture = RecordedAuditFixture.model_validate_json(text)
        except ValueError as exc:
            raise ModelConfigError(
                f"recorded audit fixture {path} is not a valid RecordedAuditFixture: {exc}"
            ) from exc
        return audit_fixture.build_client()
    raise ModelConfigError(f"no recorded constructor for role {role!r}")


def _construct_cli(role: Role, resolved: _Resolved) -> object:
    """Build the cross-provider CLI-transport client (Work Item 2 / Work Item 3).

    ``CliLlmClient`` implements the ``LlmClient`` protocol (drafting / impact /
    extraction), the ``DecompositionClient`` protocol, AND the ``AuditClient`` protocol
    (Work Item 3) — six methods total — so it is the CLI transport for ALL six roles.
    Construction never invokes the wrapper — a call does — so a configured cli role builds
    cleanly and only fails (with ``CliTransportError``) if the wrapper/contract is violated
    at run time.
    """
    from .cli_llm_client import CliLlmClient

    if not resolved.wrapper:
        raise ModelConfigError(
            f"cli transport for role {role.value} requires a wrapper (NLREQ_{role.name.upper()}_WRAPPER)"
        )
    return CliLlmClient(
        wrapper=resolved.wrapper,
        role=role,
        tier=resolved.tier,
        model_env=resolved.model_env,
        timeout_s=resolved.timeout_s,
        expected_resolved_model=resolved.expected_model,
    )


def build_client_for_role(
    role: Role,
    config: ModelConfig | None = None,
    *,
    model: str | None = None,
    fixture: Path | None = None,
    cli_override: "CliOverride | None" = None,
    force_anthropic: bool = False,
) -> BuiltClient:
    """Resolve and construct the client for a role — the CLI's single construction point.

    Args:
        role: The LLM role to build a client for.
        config: Loaded ``ModelConfig`` (from ``load_model_config``). None is treated
            as an empty config (every role falls through to the pinned constants).
        model: Per-call anthropic model-id override (highest ladder rung), e.g. from
            ``--model`` or the ``live:<model-id>`` ensemble scheme.
        fixture: Per-call recorded-fixture override (highest ladder rung), e.g. from
            ``--fixture`` or the ``recorded:<path>`` ensemble scheme.
        cli_override: Per-call cli-transport override (highest ladder rung), from the
            ``cli:<wrapper>[:<tier>|tier=<t>|model=<id>]`` ensemble/audit scheme.
        force_anthropic: Force the anthropic kind (the bare ``live`` scheme). Skips
            cli/recorded overrides and cli/recorded env/config selections so an explicit
            ``live`` never silently becomes a different transport; honors a configured
            anthropic model, else the pinned default. Never set on the default path.

    Returns:
        A ``BuiltClient`` pairing the constructed client with its ``RoleProvenance``.

    Raises:
        ModelConfigError: Unknown role/kind, a ``cli`` kind without a wrapper, a
            missing/malformed recorded fixture, or an invalid config/env selection.
    """
    if not isinstance(role, Role):
        raise ModelConfigError(f"unknown role {role!r} (expected one of {[r.value for r in Role]})")
    resolved = _resolve(
        role,
        config,
        model_override=model,
        fixture_override=fixture,
        cli_override=cli_override,
        force_anthropic=force_anthropic,
    )
    provenance = RoleProvenance(
        role=role,
        client_kind=resolved.kind,
        # resolved_model carries the concrete model id for anthropic (so the CLI can record it
        # in producer.model) and for cli (the sidecar-resolved id, Work Item 2). It is None for
        # recorded. as_metadata() emits it only for cli to avoid duplicating producer.model.
        resolved_model=resolved.model,
        prompt_version=_prompt_version_for_role(role),
        wrapper=resolved.wrapper,
        source=resolved.source,
        is_default=resolved.is_default,
        # The provider FAMILY (three-zone §3), derived from the resolved kind+wrapper. Known at
        # construction (the diversity gate runs before any call): anthropic→"anthropic",
        # cli→wrapper family, recorded→None. NOT emitted by as_metadata() (AC1 byte-identity).
        provider_family=provider_family_for(client_kind=resolved.kind, wrapper=resolved.wrapper),
    )

    if resolved.kind is ClientKind.anthropic:
        client = _construct_anthropic(role, resolved, provenance)
    elif resolved.kind is ClientKind.recorded:
        client = _construct_recorded(role, resolved)
    elif resolved.kind is ClientKind.cli:
        client = _construct_cli(role, resolved)
    else:  # pragma: no cover — ClientKind is a closed enum.
        raise ModelConfigError(f"unknown client kind {resolved.kind!r}")

    return BuiltClient(client=client, provenance=provenance)
