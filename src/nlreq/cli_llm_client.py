"""Cross-provider LLM transport via operator wrapper executables (Work Item 2 / Work Item 3).

``CliLlmClient`` implements the ``LlmClient`` protocol (drafting / impact / extraction —
three methods), the ``DecompositionClient`` protocol (one method), and the ``AuditClient``
protocol (one method), so a single class is the CLI transport for all five roles. It shells
out to an operator wrapper executable (``run-claude`` / ``run-gpt`` / ``run-gemini`` /
``run-oss`` / ``run-oss-local``) rather than importing N provider SDKs — the same
anti-corruption subprocess pattern nlreq already uses for every external verifier (slither,
foundry, go, model-checker). Auth stays in the operator's ``.env``, sourced by the wrapper;
nlreq never touches provider keys.

The operator wrappers were built for *agentic* work (ralph, ACP, review rosters), where
tool use, repo context, and soft fallback are features. In an attestation context each of
those is a provenance hazard, so every call here runs under a **pure-completion contract**:

* **No tools** — a drafting call must never touch the filesystem. The env requests no
  tools (``PI_TOOLS=""``); the sidecar's ``tools_active`` flag is the real guard, because
  some wrappers currently ignore an empty tool list (run-oss falls back to the full set).
  A wrapper whose sidecar reports ``tools_active=true`` is refused — it is attestation-
  ineligible until the operator adds a real no-tools knob (scope §6).
* **No repo/cwd context** — the wrapper runs in a scratch *empty* working directory so
  CLAUDE.md / cwd auto-load finds nothing to steer the model. The configured wrapper path is
  resolved to an ABSOLUTE executable path (``shutil.which`` + ``os.path.abspath``) BEFORE the
  scratch-cwd switch, so a relative wrapper (e.g. ``./.claude/bin/run-gpt``) is found in the
  invocation directory, not looked up in the scratch temp dir.
* **No silent fallback** — ``OSS_SOFT_FALLBACK=0`` and ``OSS_FORCE_OPENROUTER`` unset; the
  sidecar's ``route`` must equal the requested route, else the recorded model would be a
  lie and the response is refused.
* **Resolved-model provenance, never the tier** — explicit model-env exports win over the
  wrapper's ``models.env`` defaults, and the sidecar's ``resolved_model`` (the exact id
  that answered) is what provenance records.
* **Verified wrapper identity (always-on)** — nlreq independently computes the SHA-256 of the
  resolved wrapper executable (``_sha256_file``, matching the operator wrappers'
  ``_script_sha256``: raw hexdigest, no prefix) and requires the sidecar's ``wrapper_hash`` to
  equal it on EVERY call. The sidecar's hash is therefore NOT a self-reported claim a changed
  wrapper can forge: a wrapper that emits a stale/fake hash is refused even with no caller-
  supplied pin, anchoring provenance to the executable that actually ran (wrapper-drift guard).

A wrapper-side ``<output>.meta.json`` sidecar (scope §6, operator repo) is REQUIRED for
every call. Missing/invalid sidecar, ``route != requested``, ``tools_active=true``, a
missing ``resolved_model``, or a wrapper-hash mismatch (the sidecar's hash vs the
executable's independently-computed hash) each yield a ``CliTransportError`` — evidence
with unverifiable origin is exactly what nlreq exists to reject, so the client refuses
rather than fakes (same blocking semantics as the solver clients).

Conformance is exercised offline by a fixture "echo wrapper" (``tests/``); real-wrapper
tests ``skipif`` the wrapper is absent, with a recorded skip reason — the same pattern as
the apalache/forge/go real-run tests.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from pydantic import BaseModel, ConfigDict, ValidationError

from .decomposition_client import _DECOMPOSITION_PROMPT_TEMPLATE, _DECOMPOSITION_PROMPT_VERSION
from .jsonutil import sha256_text
from .llm_client import (
    build_drafting_prompt,
    build_impact_estimate_prompt,
    build_spec_extraction_prompt,
)
from .model_config import ClientKind, ModelConfigError, Role

__all__ = ["CliLlmClient", "CliTransportError", "CliSidecar"]


class CliTransportError(ModelConfigError):
    """A CLI-transport call failed or produced unverifiable-origin evidence.

    Raised on non-zero wrapper exit, timeout, a missing/invalid sidecar, a route mismatch
    (silent fallback), tool contamination (``tools_active=true``), a missing resolved
    model id, or a wrapper-hash drift. The CLI surfaces it as a refusal/error — never as
    an accepted draft — matching the blocking ``tool_error`` semantics of the solver
    clients. Subclasses ``ModelConfigError`` (a ``ValueError``) so the existing
    ``except ValueError`` handlers in the CLI catch it.
    """


class CliSidecar(BaseModel):
    """The wrapper-emitted ``<output>.meta.json`` provenance sidecar (scope §6).

    Fields are declared optional so a missing field parses (rather than raising a generic
    schema error) and is then caught by ``_load_and_validate_sidecar``'s fail-closed
    checks, which require every provenance-critical field to be present and correct:
    ``provider``, ``resolved_model``, ``route`` (== requested), ``tools_active``
    (explicitly False), ``wrapper``, ``wrapper_hash``, ``cli_version``, and
    ``duration_s``. ``extra="allow"`` so an evolving operator sidecar does not break
    parsing — the strict guards are the explicit checks, not schema closure.
    """

    model_config = ConfigDict(extra="allow")

    provider: str | None = None
    resolved_model: str | None = None
    route: str | None = None
    tools_active: bool | None = None
    wrapper: str | None = None
    wrapper_hash: str | None = None
    cli_version: str | None = None
    duration_s: float | None = None
    fallback_reason: str | None = None


def _sha256_file(path: str) -> str:
    """SHA-256 hexdigest of a file's raw bytes — the wrapper-identity anchor.

    Matches the operator wrappers' ``_script_sha256`` (``shasum -a 256 <path> | cut -d' ' -f1``):
    the raw hexdigest of the executable's bytes, with NO ``sha256:`` prefix. nlreq computes this
    from the resolved wrapper executable and requires the sidecar's ``wrapper_hash`` to equal it
    on EVERY call (always-on, iter-2 BLOCKING fix), so the sidecar's identity claim is anchored
    to the file that actually ran rather than a self-reported value a changed wrapper could
    forge. Streamed in 64 KiB chunks so a large wrapper does not load whole into memory.
    """
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


class CliLlmClient:
    """Cross-provider LLM transport via an operator wrapper executable.

    Implements ``LlmClient`` (propose_controlled_rewrite / estimate_impacted_modules /
    extract_spec_invariants) and ``DecompositionClient`` (decompose_controlled_to_ir) —
    four LlmClient/DecompositionClient methods plus the ``AuditClient`` method — so it is the
    CLI transport for the drafting, impact, extraction, decomposition, and audit roles.

    Construct with the resolved ``CliRoleSpec`` fields (wrapper, tier, model_env,
    timeout_s) plus the ``requested_route`` the caller requires (default ``official``).
    Construction never invokes the wrapper; a call does.
    """

    def __init__(
        self,
        *,
        wrapper: str,
        role: Role,
        tier: str | None = None,
        model_env: dict[str, str] | None = None,
        timeout_s: float = 120.0,
        requested_route: str = "official",
        expected_wrapper_hash: str | None = None,
        expected_resolved_model: str | None = None,
    ) -> None:
        self._wrapper = wrapper
        self._role = role
        self._tier = tier
        self._model_env: dict[str, str] = dict(model_env or {})
        self._timeout_s = timeout_s
        self._requested_route = requested_route
        self._expected_wrapper_hash = expected_wrapper_hash
        # The per-call ``cli:<wrapper>:model=<id>`` scheme pins the EXACT resolved model id the
        # sidecar must report (scope §4: provenance records the sidecar-resolved id, never the
        # tier). The operator wrappers resolve a model from wrapper+tier-specific env vars sourced
        # from ``models.env``; the per-call scheme cannot pin via env without wrapper-specific
        # knowledge, so this is a *verification* guard: the fail-closed sidecar check refuses if
        # the wrapper resolved a different model than the scheme required. Actual model selection
        # (pinning) is the config/env ``model_env`` rung's job.
        self._expected_resolved_model = expected_resolved_model
        # The last validated sidecar (None until a call succeeds). Exposed so the CLI command
        # paths can record the cli transport's resolved model/provider for the drafting/impact/
        # extraction roles (whose LlmClient-protocol methods return only text) via
        # last_call_provenance().
        self._last_sidecar: CliSidecar | None = None

    # --- LlmClient protocol -------------------------------------------------

    def propose_controlled_rewrite(
        self, prose: str, grammar_summary: str, *, language: str = "en"
    ) -> str:
        prompt = build_drafting_prompt(prose, grammar_summary, language=language)
        return self._run(prompt).text

    def estimate_impacted_modules(
        self, *, prose: str, symbols: list[str], candidate_modules: list[str]
    ) -> str:
        prompt = build_impact_estimate_prompt(
            prose=prose, symbols=symbols, candidate_modules=candidate_modules
        )
        return self._run(prompt).text

    def extract_spec_invariants(
        self, *, module_id: str, code_presentation: str, language: str = "en"
    ) -> str:
        prompt = build_spec_extraction_prompt(
            module_id=module_id, code_presentation=code_presentation, language=language
        )
        return self._run(prompt).text

    def last_call_provenance(self) -> dict[str, str]:
        """Provenance from the last VALIDATED sidecar, for stamping into artifact metadata.

        The ``LlmClient``-protocol methods (drafting / impact / extraction) return only
        text, so the sidecar's resolved model / provider / route / wrapper / wrapper_hash
        would otherwise be lost. Callers (the CLI command paths) call this AFTER a
        successful call and merge it into the produced artifact's metadata, so the cli
        transport records the sidecar-resolved model id rather than the tier (acceptance
        #4 / scope §4). Returns an empty dict until a call succeeds (``_last_sidecar`` is
        None), so the default/anthropic/recorded paths are untouched and byte-stable.
        """
        sidecar = self._last_sidecar
        if sidecar is None:
            return {}
        meta: dict[str, str] = {}
        for key, value in (
            ("resolved_model", sidecar.resolved_model),
            ("provider", sidecar.provider),
            ("route", sidecar.route),
            ("wrapper", sidecar.wrapper),
            ("wrapper_hash", sidecar.wrapper_hash),
            ("cli_version", sidecar.cli_version),
        ):
            if value is None:
                continue
            meta[key] = str(value)
        return meta

    # --- DecompositionClient protocol ---------------------------------------

    def decompose_controlled_to_ir(
        self,
        controlled_text: str,
        requirement_id: str,
        title: str,
    ):
        """Decompose via the CLI transport, returning a DecompositionResult with cli provenance.

        The wrapper's plain-text output is parsed by the deterministic ``DslV3Parser``;
        the result records the sidecar's resolved model id, provider, wrapper, and hash so
        a cross-provider ensemble's package can show two distinct providers (acceptance #2).
        """
        from .decomposition_client import DecompositionResult

        prompt = _DECOMPOSITION_PROMPT_TEMPLATE.format(
            controlled_text=controlled_text,
            requirement_id=requirement_id,
            title=title,
        )
        prompt_hash = sha256_text(prompt)
        source_text_hash = sha256_text(controlled_text)
        completion = self._run(prompt)
        sidecar = completion.sidecar

        from .dsl_v3 import DslV3Parser

        requirement = DslV3Parser().parse_ir(
            completion.text.strip(), requirement_id=requirement_id, title=title
        )
        wrapper_name = sidecar.wrapper or self._wrapper_name()
        provenance: dict[str, str] = {
            "source": "cli_decomposition",
            "client_kind": ClientKind.cli.value,
            "model": sidecar.resolved_model or "",
            "prompt_version": _DECOMPOSITION_PROMPT_VERSION,
            "wrapper": wrapper_name,
        }
        if sidecar.provider:
            provenance["provider"] = sidecar.provider
        if sidecar.route:
            provenance["route"] = sidecar.route
        if sidecar.wrapper_hash:
            provenance["wrapper_hash"] = sidecar.wrapper_hash
        return DecompositionResult(
            requirement=requirement,
            candidate_id=f"cli-{wrapper_name}-{sidecar.resolved_model}",
            source_text_hash=source_text_hash,
            model_id=sidecar.resolved_model,
            prompt_hash=prompt_hash,
            approval=None,
            is_audited=False,
            provenance=provenance,
        )

    # --- AuditClient protocol (Work Item 3) ---------------------------------

    def audit_decomposition(
        self,
        controlled_text: str,
        ir_summary: str,
    ):
        """Audit a decomposition via the CLI transport, returning an AuditVerdict.

        Implements the ``AuditClient`` protocol (Work Item 3): the wrapper's plain-text
        output is parsed as the audit JSON verdict. The verdict carries FULL CLI-transport
        provenance (ADR 0203 / ADR 0205): ``client_kind='cli'`` plus the sidecar's
        ``model_id`` / ``provider`` / ``route`` / ``wrapper`` / ``wrapper_hash`` / ``cli_version``,
        so a cross-provider audit (e.g. ``--audit-client cli:run-gpt``) records WHICH provider
        audited and under which wrapper identity — no longer just the resolved model id. An
        unparseable/schema-invalid response is a conservative failure (mirrors
        ``AnthropicAuditClient``): an unreadable audit never passes, but the sidecar provenance
        is still recorded (the call DID happen; only the verdict text was unparseable).
        """
        from .audit_client import AuditVerdict, _AUDIT_PROMPT_TEMPLATE
        from .model_config import ClientKind

        prompt = _AUDIT_PROMPT_TEMPLATE.format(
            controlled_text=controlled_text.strip(),
            ir_summary=ir_summary.strip(),
        )
        completion = self._run(prompt)
        sidecar = completion.sidecar
        raw = completion.text.strip()
        # The sidecar provenance is recorded on BOTH the pass and parse-failure paths: the call
        # happened (a validated sidecar proves it), so the audit verdict carries the wrapper
        # identity regardless of whether the verdict text parsed.
        cli_prov = {
            "client_kind": ClientKind.cli.value,
            "model_id": sidecar.resolved_model,
            "provider": sidecar.provider,
            "route": sidecar.route,
            "wrapper": sidecar.wrapper,
            "wrapper_hash": sidecar.wrapper_hash,
            "cli_version": sidecar.cli_version,
        }
        try:
            data = json.loads(raw)
            # Do NOT coerce with bool() — StrictBool rejects non-bool values (e.g. the
            # string "false") and falls through to the conservative failure below.
            return AuditVerdict(
                covers_all_clauses=data["covers_all_clauses"],
                invented_premises=list(data.get("invented_premises", [])),
                verdict=str(data["verdict"]),
                **cli_prov,
            )
        except (json.JSONDecodeError, KeyError, TypeError, ValidationError):
            # Conservative failure: an unreadable or schema-invalid audit never passes.
            return AuditVerdict(
                covers_all_clauses=False,
                invented_premises=[
                    "[audit-parse-error: model response was not valid JSON or failed schema validation]"
                ],
                verdict="failed",
                **cli_prov,
            )

    # --- transport ----------------------------------------------------------

    def _build_env(self) -> dict[str, str]:
        """The clean, explicit environment for a pure-completion call.

        PATH/HOME so the wrapper and provider CLIs resolve; the wrapper sources its own
        ``.env`` for auth (nlreq never touches provider keys). Explicit ``model_env`` exports
        are added to the process environment so they win over the wrapper's ``models.env``
        defaults (conditional-assignment form → process env wins) — this is the model-PINNING
        mechanism (scope §4): the resolved model is chosen by nlreq, not by the file default.

        The pure-completion profile (``OSS_SOFT_FALLBACK=0``, ``PI_TOOLS=""``) is applied AFTER
        ``model_env`` so it ALWAYS wins — a misconfigured ``model_env`` (e.g. one that tries to
        re-enable soft fallback or tools) cannot defeat the no-tools/no-fallback contract. The
        sidecar's ``tools_active`` / ``route`` are the enforced guards; this is defence in depth
        on the env itself.
        """
        env = {
            "PATH": os.environ.get("PATH", ""),
            "HOME": os.environ.get("HOME", ""),
            # USER/LOGNAME are non-secret user-identity vars some provider CLIs need for
            # keychain-backed auth (e.g. claude's OAuth fallback when no API key is sourced
            # from .env). They are NOT context that steers the model (the scratch empty cwd +
            # the wrapper's pure-completion flags handle that) and NOT secrets.
            "USER": os.environ.get("USER", ""),
            "LOGNAME": os.environ.get("LOGNAME", ""),
        }
        # NLREQ_ATTESTATION=1 is the universal signal that switches an operator wrapper into
        # attestation mode (scope §6 / ADR 0203): the wrapper adopts its pure-completion CLI
        # profile (no tools / no cwd-repo context / no silent fallback) AND emits the
        # <output>.meta.json sidecar this client requires. Agentic callers (ralph, ACP) leave
        # it unset, so they are byte-unchanged — the sidecar + pure profile are opt-in per call.
        env["NLREQ_ATTESTATION"] = "1"
        # Operator model-pinning exports win over the wrapper's models.env defaults.
        env.update(self._model_env)
        # Pure-completion profile — applied AFTER model_env so it is non-negotiable. The sidecar's
        # tools_active/route are the real guards; this ensures the env itself cannot be subverted.
        env["OSS_SOFT_FALLBACK"] = "0"
        # OSS_FORCE_OPENROUTER intentionally absent: unset == official-first routing.
        env["PI_TOOLS"] = ""  # no-tools request; sidecar tools_active is the real guard.
        return env

    def _wrapper_name(self) -> str:
        """The wrapper's identity label: the basename of the configured wrapper.

        Operators configure either a bare name (``run-claude``, on PATH) or an absolute
        path; the basename is the stable identity recorded in provenance (``run-claude``),
        with ``wrapper_hash`` as the disambiguator between same-named wrappers.
        """
        return os.path.basename(self._wrapper)

    def _resolve_wrapper(self) -> str:
        """Resolve the wrapper to an ABSOLUTE executable path before the scratch-cwd switch.

        ``shutil.which`` handles all three configured forms — a bare name (PATH search), a
        relative path (resolved against the INVOCATION cwd and made absolute), and an absolute
        path — and checks the executable bit, so the returned path is always absolute and
        executable. Resolving to absolute BEFORE ``_run`` switches to the scratch empty cwd is
        critical (iter-2 BLOCKING fix): a relative wrapper such as ``./.claude/bin/run-gpt`` or
        ``tools/run-gpt`` executed with ``cwd=scratch_dir`` would otherwise be looked up relative
        to the scratch temp directory (an uncaught ``FileNotFoundError``), not the invocation
        directory the operator configured. An absolute path also makes the wrapper's own
        ``sys.argv[0]`` absolute, so the wrapper's self-computed hash reads the same file nlreq
        hashes (see ``_sha256_file`` / the always-on sidecar check).
        """
        found = shutil.which(self._wrapper)
        if found is None:
            raise CliTransportError(
                f"cli wrapper {self._wrapper!r} not found or not executable "
                f"(role={self._role.value}); bare names are searched on PATH, relative/absolute "
                "paths are resolved against the invocation cwd and require the executable bit"
            )
        # ``shutil.which`` returns a relative path VERBATIM for a relative ``cmd`` (it only
        # checks the executable bit, it does not absolutize), so make it absolute here against
        # the invocation cwd — before ``_run`` switches to the scratch cwd. (For a bare name on
        # PATH or an absolute path, ``found`` is already absolute and this is a no-op.)
        return os.path.abspath(found)

    def _run(self, prompt: str) -> "_Completion":
        """Invoke the wrapper under the pure-completion contract and validate the sidecar.

        Writes the prompt to a temp input file in a scratch EMPTY working directory (defeats
        CLAUDE.md/cwd context auto-load), invokes ``<wrapper> <input> <output> [--tier]``
        with the clean env, and requires a ``<output>.meta.json`` sidecar. Non-zero exit,
        timeout, or any sidecar contract violation → ``CliTransportError`` (blocks, never
        fakes).
        """
        wrapper_path = self._resolve_wrapper()
        # Always-on wrapper-hash anchoring (iter-2 BLOCKING fix): nlreq independently computes
        # the SHA-256 of the resolved wrapper executable BEFORE invoking it, then requires the
        # sidecar's ``wrapper_hash`` to match (see ``_load_and_validate_sidecar``). This anchors
        # provenance to the executable that actually ran — the sidecar's hash is no longer a
        # self-reported claim a changed/lying wrapper can forge. Matches the operator wrappers'
        # ``_script_sha256`` (shasum -a 256 of the script → raw hexdigest), so run-claude/run-gpt
        # report the same hash nlreq computes.
        try:
            actual_wrapper_hash = _sha256_file(wrapper_path)
        except OSError as exc:
            raise CliTransportError(
                f"cli wrapper {self._wrapper!r} executable {wrapper_path!r} could not be hashed "
                f"(role={self._role.value}): {exc}"
            ) from exc
        # Scratch empty cwd so the wrapper's cwd-context auto-load (CLAUDE.md, settings,
        # hooks) finds nothing. Input/output are absolute paths inside it.
        scratch_dir = Path(tempfile.mkdtemp(prefix="nlreq-cli-llm-"))
        try:
            input_path = scratch_dir / "prompt.txt"
            output_path = scratch_dir / "completion.txt"
            input_path.write_text(prompt, encoding="utf-8")

            argv = [wrapper_path, str(input_path), str(output_path)]
            if self._tier is not None:
                argv += ["--tier", self._tier]

            try:
                proc = subprocess.run(
                    argv,
                    cwd=str(scratch_dir),
                    env=self._build_env(),
                    capture_output=True,
                    text=True,
                    timeout=self._timeout_s,
                    check=False,
                )
            except subprocess.TimeoutExpired as exc:
                raise CliTransportError(
                    f"cli wrapper {self._wrapper!r} timed out after {self._timeout_s}s "
                    f"(role={self._role.value}): {exc}"
                ) from exc
            except OSError as exc:
                # Defence in depth (iter-2 BLOCKING fix): ``_resolve_wrapper`` already verified
                # the executable exists + is executable, but a race (file removed between resolve
                # and exec) or an exec-level failure must still surface as a structured refusal —
                # never an uncaught ``FileNotFoundError``/``OSError`` that escapes the
                # ``CliTransportError`` contract (the "structured refusal, no silent fallback" shape).
                raise CliTransportError(
                    f"cli wrapper {self._wrapper!r} could not be executed "
                    f"(role={self._role.value}): {exc}"
                ) from exc

            if proc.returncode != 0:
                stderr = (proc.stderr or "").strip()
                raise CliTransportError(
                    f"cli wrapper {self._wrapper!r} exited {proc.returncode} "
                    f"(role={self._role.value}); stderr: {stderr[:2000]}"
                )

            if not output_path.is_file():
                raise CliTransportError(
                    f"cli wrapper {self._wrapper!r} exited 0 but wrote no output file "
                    f"{output_path} (role={self._role.value})"
                )
            text = output_path.read_text(encoding="utf-8")

            sidecar = self._load_and_validate_sidecar(output_path, actual_wrapper_hash)
            self._last_sidecar = sidecar
            return _Completion(text=text, sidecar=sidecar)
        finally:
            shutil.rmtree(scratch_dir, ignore_errors=True)

    def _load_and_validate_sidecar(
        self, output_path: Path, actual_wrapper_hash: str
    ) -> CliSidecar:
        """Load ``<output>.meta.json`` and enforce the pure-completion contract (fail-closed).

        Every provenance-critical field is REQUIRED and validated: a wrapper that omits
        ``provider`` / ``resolved_model`` / ``route`` / ``wrapper`` / ``wrapper_hash`` /
        ``cli_version`` / ``duration_s`` produces evidence with unverifiable origin and is
        refused — the sidecar contract is fail-closed, not fail-open. Each guard maps to a
        scope acceptance criterion: a missing field, a route mismatch (silent fallback),
        tool contamination (``tools_active`` not explicitly False), or a wrapper-hash drift
        each refuse the response rather than accepting a draft built on unverifiable origin.
        """
        sidecar_path = Path(str(output_path) + ".meta.json")
        if not sidecar_path.is_file():
            raise CliTransportError(
                f"cli wrapper {self._wrapper!r} produced no meta sidecar {sidecar_path} "
                f"(role={self._role.value}); a sidecar is required for attestation provenance"
            )
        try:
            data = json.loads(sidecar_path.read_text(encoding="utf-8"))
        except (ValueError, OSError) as exc:
            raise CliTransportError(
                f"cli wrapper {self._wrapper!r} sidecar {sidecar_path} is not valid JSON: {exc}"
            ) from exc
        try:
            sidecar = CliSidecar.model_validate(data)
        except ValidationError as exc:
            raise CliTransportError(
                f"cli wrapper {self._wrapper!r} sidecar {sidecar_path} failed schema validation: {exc}"
            ) from exc

        # Fail-closed: every provenance-critical field MUST be present and non-empty. A wrapper
        # that omits any of these (provider, resolved model, route, wrapper identity, wrapper hash,
        # CLI version, duration) cannot prove the origin of its answer — exactly what nlreq exists
        # to reject. ``resolved_model`` is included here so a null/empty model id refuses even
        # before the dedicated guard below (defence in depth).
        required_fields: list[tuple[str, object]] = [
            ("provider", sidecar.provider),
            ("resolved_model", sidecar.resolved_model),
            ("route", sidecar.route),
            ("wrapper", sidecar.wrapper),
            ("wrapper_hash", sidecar.wrapper_hash),
            ("cli_version", sidecar.cli_version),
            ("duration_s", sidecar.duration_s),
        ]
        for name, value in required_fields:
            if value is None or (isinstance(value, str) and not value.strip()):
                raise CliTransportError(
                    f"cli wrapper {self._wrapper!r} sidecar lacks {name} (role={self._role.value}); "
                    "a wrapper that omits a provenance-critical field produces evidence with "
                    "unverifiable origin — the sidecar contract is fail-closed"
                )

        # Always-on wrapper-hash verification (iter-2 BLOCKING fix): the sidecar's
        # ``wrapper_hash`` MUST equal the SHA-256 nlreq computed from the resolved executable
        # (``actual_wrapper_hash``). This is the core wrapper-drift guard — a wrapper that emits
        # a stale/fake hash is refused even when no ``expected_wrapper_hash`` pin was supplied,
        # because the sidecar no longer gets to self-report its identity: nlreq anchors it to the
        # executable that actually ran. Matches the operator wrappers' ``_script_sha256``, so the
        # eligible wrappers (run-claude/run-gpt) report the same hash nlreq computes.
        if sidecar.wrapper_hash != actual_wrapper_hash:
            raise CliTransportError(
                f"cli wrapper {self._wrapper!r} hash mismatch: sidecar wrapper_hash "
                f"{sidecar.wrapper_hash!r} != executable file hash {actual_wrapper_hash!r} "
                f"(role={self._role.value}); the sidecar must report the SHA-256 of the wrapper "
                "executable that actually ran — a stale/fake hash is refused (wrapper drift)"
            )

        # route must equal the requested route: a different route means a silent provider/model
        # fallback answered, so the recorded model would be a lie.
        if sidecar.route != self._requested_route:
            raise CliTransportError(
                f"cli wrapper {self._wrapper!r} route mismatch: sidecar route "
                f"{sidecar.route!r} != requested {self._requested_route!r} "
                f"(role={self._role.value}); a silent provider/model fallback is a provenance hazard"
            )

        # tools_active must be an EXPLICIT False (not None, not True). None means the wrapper did
        # not assert the no-tools guarantee — attestation-ineligible until it does (scope §6).
        if sidecar.tools_active is None:
            raise CliTransportError(
                f"cli wrapper {self._wrapper!r} sidecar lacks tools_active (role={self._role.value}); "
                "the no-tools guarantee must be an explicit boolean assertion, not an omission"
            )
        if sidecar.tools_active is True:
            raise CliTransportError(
                f"cli wrapper {self._wrapper!r} ran with tools active (role={self._role.value}); "
                "a drafting/decomposition call must never be able to touch the filesystem — "
                "the wrapper is attestation-ineligible until it honors the pure-completion profile (scope §6)"
            )

        # Per-call resolved-model verification (scope §4: provenance records the sidecar-resolved
        # id, never the tier). When the caller pins an expected model (``cli:<wrapper>:model=<id>``),
        # the sidecar's resolved_model MUST equal it — a wrapper that resolved a different model
        # than the scheme required is a provenance hazard (the recorded model would not match the
        # requested one). Pinning the model itself is the config/env ``model_env`` rung's job; this
        # guard makes the per-call scheme assert exactly which model answered.
        if (
            self._expected_resolved_model is not None
            and sidecar.resolved_model != self._expected_resolved_model
        ):
            raise CliTransportError(
                f"cli wrapper {self._wrapper!r} resolved model mismatch: sidecar resolved_model "
                f"{sidecar.resolved_model!r} != expected {self._expected_resolved_model!r} "
                f"(role={self._role.value}); provenance must record the model the per-call scheme "
                "required — pin the model via config/env model_env if the wrapper resolved the wrong one"
            )

        # Optional known-good wrapper pin (``expected_wrapper_hash``): when the caller pins a
        # known-good hash, a mismatch refuses. The always-on check above already proved
        # ``sidecar.wrapper_hash == actual_wrapper_hash`` (the executable's real hash), so this
        # guard pins the EXECUTABLE itself to a known-good version — it catches a swapped wrapper
        # even if the sidecar honestly reports the new (different) hash. The factory/CLI do not
        # currently set this; it is a defensive pin for future config-driven version pinning.
        if (
            self._expected_wrapper_hash is not None
            and sidecar.wrapper_hash != self._expected_wrapper_hash
        ):
            raise CliTransportError(
                f"cli wrapper {self._wrapper!r} hash drift: sidecar wrapper_hash "
                f"{sidecar.wrapper_hash!r} != pinned expected {self._expected_wrapper_hash!r} "
                f"(role={self._role.value}); the wrapper executable does not match the known-good pinned hash"
            )
        return sidecar


class _Completion:
    """A wrapper completion: the output text plus its validated provenance sidecar."""

    __slots__ = ("text", "sidecar")

    def __init__(self, text: str, sidecar: CliSidecar) -> None:
        self.text = text
        self.sidecar = sidecar
