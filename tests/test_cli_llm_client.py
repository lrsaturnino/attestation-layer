"""Conformance tests for Work Item 2: the CliLlmClient cross-provider transport.

These run fully offline against a fixture "echo wrapper" (scope §4) that mimics the
operator run-* wrapper contract — ``<input> <output> [--tier]`` plus a
``<output>.meta.json`` sidecar — and is steered by an ``ECHO_MODE`` env var (passed
through the client's ``model_env``). They pin the pure-completion contract:

* a valid sidecar round-trips for all four methods (drafting / impact / extraction /
  decomposition), and the decomposition result records the sidecar's provider / resolved
  model / wrapper / hash (acceptance #2's intent);
* a missing sidecar, a route mismatch (silent fallback), ``tools_active=true``, a missing
  resolved model, a non-zero exit, or a wrapper-hash drift each raise CliTransportError —
  a structured refusal, never an accepted draft (acceptance #3).

Real-wrapper tests skip unless ``NLREQ_RUN_REAL_WRAPPER_TESTS=1`` is set: they need the
operator's auth + the §6 sidecar change (operator repo), so they are not CI-safe.
"""
from __future__ import annotations

import hashlib
import json
import os
import stat
from pathlib import Path

import pytest

from nlreq.cli import main
from nlreq.cli_llm_client import CliLlmClient, CliTransportError
from nlreq.decomposition_client import _DECOMPOSITION_PROMPT_VERSION
from nlreq.llm_client import _DRAFTING_PROMPT_VERSION, _IMPACT_PROMPT_VERSION
from nlreq.model_config import Role

# A canned valid DSL v3 completion the echo wrapper returns. Known-parseable (it is the
# same shape the offline LLM/semantic tests use), so it serves both the text-returning
# LlmClient methods and the parsing DecompositionClient method.
_CANNED_COMPLETION = (
    "requirement authorization_precondition:\n"
    "scope operation\n"
    "when actor is not authorized\n"
    "then operation must reject before state_change\n"
)
_CONTROLLED = _CANNED_COMPLETION

def _echo_wrapper_script(
    *,
    provider: str = "echo",
    model: str = "echo-model-snapshot-20260601",
    wrapper_name: str = "echo-wrapper",
    output_text: str = _CANNED_COMPLETION,
) -> str:
    """Build the echo wrapper script with baked-in sidecar values for the 'ok' mode.

    The wrapper writes a COMPLETE sidecar (all provenance-critical fields) by default and
    per-mode overrides exactly one concern, so each refusal test exercises the intended
    guard rather than tripping a different fail-closed check first. ``wrapper_hash`` is NOT
    baked in: the script computes the SHA-256 of its OWN file (``sys.argv[0]``) at run time,
    exactly as the real operator wrappers do (``_script_sha256`` via ``shasum -a 256``), so
    nlreq's always-on executable-hash verification (iter-2) passes for the 'ok' path and only
    the ``hash_drift`` mode emits a fake hash to exercise the refusal. ``ECHO_MODE`` (passed
    through the client's ``model_env``) selects the mode. The ``cli:`` scheme passes only
    wrapper+tier (no env), so a multi-provider ensemble test needs two distinct wrapper
    scripts that report different providers/models.
    """
    return (
        '#!/usr/bin/env python3\n'
        '"""Offline echo wrapper for CliLlmClient conformance tests (scope §4)."""\n'
        'import hashlib, json, os, sys\n'
        'out = sys.argv[2]\n'
        'mode = os.environ.get("ECHO_MODE", "ok")\n'
        'exit_code = 0\n'
        'with open(out, "w") as f:\n'
        '    f.write(%r)\n'
        '# The wrapper reports its OWN file content hash — the same anchor nlreq computes\n'
        '# independently (_sha256_file) and requires the sidecar to match (iter-2 always-on\n'
        '# verification). hash_drift mode overrides this with a fake hash to exercise the refusal.\n'
        'own_hash = hashlib.sha256(open(sys.argv[0], "rb").read()).hexdigest()\n'
        'sidecar_path = out + ".meta.json"\n'
        '# Base valid sidecar — every provenance-critical field present and correct.\n'
        'sidecar = {"resolved_model": %r, "route": "official", "tools_active": False, '
        '"provider": %r, "wrapper": %r, "wrapper_hash": own_hash, "cli_version": "echo-1.0", "duration_s": 0.01}\n'
        'if mode == "no_sidecar":\n'
        '    pass  # write no sidecar\n'
        'elif mode == "bad_route":\n'
        '    sidecar["route"] = "openrouter"\n'
        '    json.dump(sidecar, open(sidecar_path, "w"))\n'
        'elif mode == "tools":\n'
        '    sidecar["tools_active"] = True\n'
        '    json.dump(sidecar, open(sidecar_path, "w"))\n'
        'elif mode == "no_model":\n'
        '    sidecar["resolved_model"] = None\n'
        '    json.dump(sidecar, open(sidecar_path, "w"))\n'
        'elif mode == "fail":\n'
        '    sys.stderr.write("simulated wrapper failure\\n")\n'
        '    exit_code = 1\n'
        'elif mode == "hash_drift":\n'
        '    sidecar["wrapper_hash"] = "stale-hash"\n'
        '    json.dump(sidecar, open(sidecar_path, "w"))\n'
        'elif mode == "record_cwd":\n'
        '    sidecar["cwd"] = os.getcwd()\n'
        '    json.dump(sidecar, open(sidecar_path, "w"))\n'
        'else:\n'
        '    # ok + per-field-omission modes (no_provider / no_wrapper / no_wrapper_hash /\n'
        '    # no_cli_version / no_duration / no_route / no_tools_flag): drop the named field.\n'
        '    drop = mode[3:] if mode.startswith("no_") else None\n'
        '    if drop is not None and drop != "model":\n'
        '        sidecar.pop(drop, None)\n'
        '    json.dump(sidecar, open(sidecar_path, "w"))\n'
        'sys.exit(exit_code)\n'
    ) % (output_text, model, provider, wrapper_name)


def _make_echo_wrapper(
    tmp_path: Path,
    *,
    name: str = "echo-wrapper",
    provider: str = "echo",
    model: str = "echo-model-snapshot-20260601",
    wrapper_name: str = "echo-wrapper",
    output_text: str = _CANNED_COMPLETION,
) -> Path:
    """Write the echo wrapper script to tmp_path, chmod +x, and return its path.

    ``wrapper_hash`` is intentionally NOT a parameter: the script computes its own file hash
    at run time (matching the real operator wrappers' ``_script_sha256``), so nlreq's
    always-on executable-hash verification passes. Tests that assert the recorded hash use
    ``_file_sha256(wrapper)``.
    """
    path = tmp_path / name
    path.write_text(
        _echo_wrapper_script(
            provider=provider, model=model, wrapper_name=wrapper_name,
            output_text=output_text,
        ),
        encoding="utf-8",
    )
    os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return path


def _file_sha256(path: Path) -> str:
    """The SHA-256 nlreq's always-on check computes from the wrapper executable (iter-2).

    Mirrors ``cli_llm_client._sha256_file`` and the operator wrappers' ``_script_sha256``: the
    raw hexdigest of the file's bytes (no ``sha256:`` prefix). Tests assert the recorded
    ``wrapper_hash`` equals this, proving the sidecar identity is anchored to the executable
    that actually ran rather than a self-reported claim.
    """
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _client(wrapper: Path | str, *, mode: str, role: Role = Role.drafting, **kwargs) -> CliLlmClient:
    """Build a CliLlmClient whose model_env carries ECHO_MODE to the echo wrapper."""
    return CliLlmClient(
        wrapper=str(wrapper),
        role=role,
        model_env={"ECHO_MODE": mode},
        timeout_s=30.0,
        **kwargs,
    )


def _clear_model_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Strip every NLREQ_<ROLE>_* / NLREQ_MODEL_CONFIG env var for a clean ladder baseline."""
    for role in Role:
        prefix = f"NLREQ_{role.name.upper()}"
        for suffix in ("CLIENT", "MODEL", "WRAPPER", "TIER", "FIXTURE", "MODEL_ENV", "TIMEOUT_S"):
            monkeypatch.delenv(f"{prefix}_{suffix}", raising=False)
    monkeypatch.delenv("NLREQ_MODEL_CONFIG", raising=False)


# ---------------------------------------------------------------------------
# Round-trips (acceptance #2 intent: sidecar provenance recorded)
# ---------------------------------------------------------------------------


def test_propose_controlled_rewrite_round_trip(tmp_path: Path) -> None:
    wrapper = _make_echo_wrapper(tmp_path)
    client = _client(wrapper, mode="ok")
    text = client.propose_controlled_rewrite("some prose", "grammar summary", language="en")
    assert text == _CANNED_COMPLETION


def test_estimate_impacted_modules_round_trip(tmp_path: Path) -> None:
    wrapper = _make_echo_wrapper(tmp_path)
    client = _client(wrapper, mode="ok", role=Role.impact)
    text = client.estimate_impacted_modules(
        prose="prose", symbols=["a"], candidate_modules=["m1", "m2"]
    )
    assert text == _CANNED_COMPLETION


def test_extract_spec_invariants_round_trip(tmp_path: Path) -> None:
    wrapper = _make_echo_wrapper(tmp_path)
    client = _client(wrapper, mode="ok", role=Role.extraction)
    text = client.extract_spec_invariants(
        module_id="m", code_presentation="code", language="go"
    )
    assert text == _CANNED_COMPLETION


def test_decompose_controlled_to_ir_records_sidecar_provenance(tmp_path: Path) -> None:
    """The decomposition result records the sidecar's provider/model/wrapper/hash (acceptance #2)."""
    wrapper = _make_echo_wrapper(tmp_path)
    client = _client(wrapper, mode="ok", role=Role.decomposition)
    result = client.decompose_controlled_to_ir(
        _CONTROLLED, requirement_id="R-ECHO", title="echo"
    )
    assert result.candidate_id == "cli-echo-wrapper-echo-model-snapshot-20260601"
    assert result.model_id == "echo-model-snapshot-20260601"
    assert result.provenance["client_kind"] == "cli"
    assert result.provenance["source"] == "cli_decomposition"
    assert result.provenance["model"] == "echo-model-snapshot-20260601"
    assert result.provenance["provider"] == "echo"
    assert result.provenance["wrapper"] == "echo-wrapper"
    assert result.provenance["wrapper_hash"] == _file_sha256(wrapper)
    assert result.provenance["prompt_version"] == _DECOMPOSITION_PROMPT_VERSION
    # The deterministic parser produced a real IR from the model's re-expression.
    assert result.requirement.requirement_id == "R-ECHO"


def test_audit_decomposition_round_trip_records_sidecar_model(tmp_path: Path) -> None:
    """The audit CLI transport parses the wrapper's JSON verdict and records FULL sidecar
    provenance (ADR 0203 / ADR 0205).

    Work Item 3: ``CliLlmClient`` implements the ``AuditClient`` protocol. The verdict carries
    ``client_kind='cli'`` plus the sidecar's ``model_id`` / ``provider`` / ``route`` / ``wrapper`` /
    ``wrapper_hash`` / ``cli_version``, so a cross-provider audit records WHICH provider audited
    AND under which wrapper identity — not just the resolved model id.
    """
    audit_json = json.dumps(
        {"covers_all_clauses": True, "invented_premises": [], "verdict": "passed"}
    )
    wrapper = _make_echo_wrapper(
        tmp_path, name="echo-audit", model="audit-model-snap",
        wrapper_name="run-audit", output_text=audit_json,
    )
    client = _client(wrapper, mode="ok", role=Role.audit)
    verdict = client.audit_decomposition("controlled text", "ir summary")
    assert verdict.verdict == "passed"
    assert verdict.covers_all_clauses is True
    assert verdict.invented_premises == []
    assert verdict.model_id == "audit-model-snap"  # sidecar-resolved model id, not a tier
    # Full CLI-transport provenance (ADR 0205) — no longer just model_id.
    assert verdict.client_kind == "cli"
    assert verdict.provider == "echo"
    assert verdict.route == "official"
    assert verdict.wrapper == "run-audit"
    assert verdict.wrapper_hash == _file_sha256(wrapper)
    assert verdict.cli_version == "echo-1.0"


def test_audit_decomposition_parse_failure_is_conservative(tmp_path: Path) -> None:
    """An unparseable audit response is a conservative failure, never a pass.

    The sidecar provenance is STILL recorded on a parse failure (ADR 0205): the call happened
    (a validated sidecar proves it), so the verdict carries the wrapper identity regardless of
    whether the verdict text parsed — only the verdict is conservative, not the provenance.
    """
    wrapper = _make_echo_wrapper(
        tmp_path, name="echo-audit-bad", output_text="not json at all",
    )
    client = _client(wrapper, mode="ok", role=Role.audit)
    verdict = client.audit_decomposition("controlled text", "ir summary")
    assert verdict.verdict == "failed"
    assert verdict.covers_all_clauses is False
    # The sidecar-resolved model id is still recorded even on a parse failure.
    assert verdict.model_id == "echo-model-snapshot-20260601"
    # Full CLI provenance is recorded on the parse-failure path too (the call DID happen).
    assert verdict.client_kind == "cli"
    assert verdict.provider == "echo"


# ---------------------------------------------------------------------------
# Pure-completion contract refusals (acceptance #3: never an accepted draft)
# ---------------------------------------------------------------------------


def test_missing_sidecar_refuses(tmp_path: Path) -> None:
    wrapper = _make_echo_wrapper(tmp_path)
    client = _client(wrapper, mode="no_sidecar")
    with pytest.raises(CliTransportError, match="no meta sidecar"):
        client.propose_controlled_rewrite("prose", "grammar")


def test_route_mismatch_refuses(tmp_path: Path) -> None:
    """A sidecar route != requested (silent provider fallback) is refused."""
    wrapper = _make_echo_wrapper(tmp_path)
    client = _client(wrapper, mode="bad_route")  # sidecar route=openrouter, requested=official
    with pytest.raises(CliTransportError, match="route mismatch"):
        client.propose_controlled_rewrite("prose", "grammar")


def test_tools_active_refuses(tmp_path: Path) -> None:
    """A tool-enabled wrapper profile (tools_active=true) is refused."""
    wrapper = _make_echo_wrapper(tmp_path)
    client = _client(wrapper, mode="tools")
    with pytest.raises(CliTransportError, match="tools active"):
        client.propose_controlled_rewrite("prose", "grammar")


def test_missing_resolved_model_refuses(tmp_path: Path) -> None:
    """A sidecar without resolved_model is refused (provenance can't record the model)."""
    wrapper = _make_echo_wrapper(tmp_path)
    client = _client(wrapper, mode="no_model")
    with pytest.raises(CliTransportError, match="lacks resolved_model"):
        client.propose_controlled_rewrite("prose", "grammar")


def test_nonzero_exit_refuses(tmp_path: Path) -> None:
    """A non-zero wrapper exit is a blocking tool_error, never a faked completion."""
    wrapper = _make_echo_wrapper(tmp_path)
    client = _client(wrapper, mode="fail")
    with pytest.raises(CliTransportError, match="exited 1"):
        client.propose_controlled_rewrite("prose", "grammar")


def test_wrapper_hash_drift_refuses_without_pin(tmp_path: Path) -> None:
    """A sidecar ``wrapper_hash`` != the executable's actual SHA-256 is refused on EVERY call —
    no ``expected_wrapper_hash`` pin is needed (iter-2 always-on verification).

    The echo wrapper's ``hash_drift`` mode emits a fake ``'stale-hash'``; nlreq independently
    hashed the resolved executable and refuses the mismatch, so a changed/lying wrapper can
    never be accepted as provenance. This is the core wrapper-drift guard the prior iteration
    lacked (the sidecar's hash was a self-reported claim)."""
    wrapper = _make_echo_wrapper(tmp_path)
    client = _client(wrapper, mode="hash_drift")  # no expected_wrapper_hash pin
    with pytest.raises(CliTransportError, match="hash mismatch"):
        client.propose_controlled_rewrite("prose", "grammar")


def test_pinned_wrapper_hash_mismatch_refuses(tmp_path: Path) -> None:
    """A caller-supplied ``expected_wrapper_hash`` pin refuses when the executable's hash differs
    from the known-good pin — catching a swapped wrapper even if the sidecar honestly reports
    the new (different) hash. The always-on check passes (sidecar == file), but the pin fails."""
    wrapper = _make_echo_wrapper(tmp_path)
    client = _client(
        wrapper, mode="ok", expected_wrapper_hash="a-known-good-hash-that-is-not-the-file"
    )
    with pytest.raises(CliTransportError, match="hash drift"):
        client.propose_controlled_rewrite("prose", "grammar")


def test_wrapper_not_found_refuses(tmp_path: Path) -> None:
    """A wrapper absent from PATH refuses (deterministic, no API fallback)."""
    client = CliLlmClient(
        wrapper="nlreq-definitely-not-on-path-xyz",
        role=Role.drafting,
        timeout_s=5.0,
    )
    with pytest.raises(CliTransportError, match="not found"):
        client.propose_controlled_rewrite("prose", "grammar")


def test_relative_wrapper_path_resolves_against_invocation_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A relative wrapper path is resolved against the INVOCATION cwd, not the scratch cwd.

    Regression for the iter-2 BLOCKING fix: ``_resolve_wrapper`` makes the path absolute (via
    ``shutil.which``, which resolves a relative path against the current cwd) BEFORE ``_run``
    switches to the scratch empty cwd, so ``./echo-rel`` finds the wrapper in the invocation
    directory. Before the fix the relative path was passed verbatim and ``subprocess.run`` with
    ``cwd=scratch_dir`` looked it up in the scratch temp dir — an uncaught ``FileNotFoundError``
    that escaped the ``CliTransportError`` structured-refusal contract.
    """
    wrapper = _make_echo_wrapper(tmp_path, name="echo-rel")
    monkeypatch.chdir(tmp_path)  # invocation cwd = tmp_path (where echo-rel lives)
    client = CliLlmClient(
        wrapper="./echo-rel", role=Role.drafting,
        model_env={"ECHO_MODE": "ok"}, timeout_s=30.0,
    )
    text = client.propose_controlled_rewrite("prose", "grammar")
    assert text == _CANNED_COMPLETION


def test_missing_relative_wrapper_refuses_structurally(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A relative wrapper that does not exist refuses as ``CliTransportError`` (not an uncaught
    ``FileNotFoundError``) — the structured-refusal shape holds for relative paths too.

    ``_resolve_wrapper`` returns None for a missing relative path (``shutil.which`` finds no
    executable), so the call refuses before any subprocess is attempted.
    """
    monkeypatch.chdir(tmp_path)
    client = CliLlmClient(wrapper="./no-such-wrapper", role=Role.drafting, timeout_s=5.0)
    with pytest.raises(CliTransportError, match="not found"):
        client.propose_controlled_rewrite("prose", "grammar")


@pytest.mark.parametrize(
    "field",
    ["provider", "route", "wrapper", "wrapper_hash", "cli_version", "duration_s", "tools_active"],
)
def test_sidecar_missing_required_field_refuses(tmp_path: Path, field: str) -> None:
    """Fail-closed contract: omitting any provenance-critical field refuses (acceptance #3).

    Each mode (``no_<field>``) drops exactly one required field from an otherwise-complete
    sidecar so the intended guard fires (not a different fail-closed check). A wrapper that
    omits provider / route / wrapper / wrapper_hash / cli_version / duration_s / tools_active
    produces evidence with unverifiable origin and is refused — never an accepted draft.
    """
    wrapper = _make_echo_wrapper(tmp_path)
    client = _client(wrapper, mode=f"no_{field}")
    with pytest.raises(CliTransportError, match=f"lacks {field}"):
        client.propose_controlled_rewrite("prose", "grammar")


def test_scratch_empty_cwd_is_used(tmp_path: Path) -> None:
    """The wrapper runs in a fresh scratch cwd (no repo/CLAUDE.md context auto-load)."""
    wrapper = _make_echo_wrapper(tmp_path)
    client = _client(wrapper, mode="record_cwd")
    text = client.propose_controlled_rewrite("prose", "grammar")
    assert text == _CANNED_COMPLETION  # sidecar was valid; the cwd was recorded in it
    # The last sidecar's cwd is a fresh temp dir (the mkdtemp prefix), not the test cwd.
    sidecar_cwd = client._last_sidecar.cwd  # type: ignore[attr-defined]
    assert "nlreq-cli-llm-" in sidecar_cwd
    assert Path(sidecar_cwd) != Path.cwd()


# ---------------------------------------------------------------------------
# Cross-provider ensemble via the cli: scheme (acceptance #2)
# ---------------------------------------------------------------------------


def test_cli_cross_provider_ensemble_records_two_distinct_providers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Acceptance #2: a cli:run-A + cli:run-B ensemble records two distinct providers,
    resolved model ids, wrapper hashes, and prompt versions in the report.

    Two echo wrappers report different providers/models/hashes; both return the same
    canned IR so the ensemble agrees, but both are unaudited (CliLlmClient always
    produces is_audited=False) → the report is needs-review (exit 1), not exit 2. The
    candidate provenances still flow into ``ensemble_candidate_provenances`` (populated
    before the trust check), proving the cross-provider diversity is recorded.
    """
    for role in Role:
        prefix = f"NLREQ_{role.name.upper()}"
        for suffix in ("CLIENT", "MODEL", "WRAPPER", "TIER", "FIXTURE"):
            monkeypatch.delenv(f"{prefix}_{suffix}", raising=False)
    monkeypatch.delenv("NLREQ_MODEL_CONFIG", raising=False)

    wrapper_a = _make_echo_wrapper(
        tmp_path, name="echo-a", provider="alpha-provider", model="alpha-model-snap",
        wrapper_name="run-alpha",
    )
    wrapper_b = _make_echo_wrapper(
        tmp_path, name="echo-b", provider="beta-provider", model="beta-model-snap",
        wrapper_name="run-beta",
    )
    req = tmp_path / "req.nlreq"
    req.write_text(_CONTROLLED)
    out = tmp_path / "report.json"

    exit_code = main([
        "semantic-translate", str(req),
        "--requirement-id", "R-CP",
        "--title", "cross-provider",
        "--ensemble-client", f"cli:{wrapper_a}",
        "--ensemble-client", f"cli:{wrapper_b}",
        "--out", str(out),
    ])
    assert exit_code in (0, 1), f"expected 0/1 (agreement, unaudited), got {exit_code}"
    report = json.loads(out.read_text())
    candidate_provs: list[dict] = report.get("ensemble_candidate_provenances", [])
    assert len(candidate_provs) == 2, f"expected 2 candidates, got {len(candidate_provs)}"

    providers = {cp.get("provider") for cp in candidate_provs}
    models = {cp.get("model") for cp in candidate_provs}
    wrappers = {cp.get("wrapper") for cp in candidate_provs}
    hashes = {cp.get("wrapper_hash") for cp in candidate_provs}
    assert providers == {"alpha-provider", "beta-provider"}
    assert models == {"alpha-model-snap", "beta-model-snap"}
    assert wrappers == {"run-alpha", "run-beta"}
    # The recorded hashes are the EXECUTABLES' actual SHA-256 (nlreq's always-on verification),
    # so they equal what nlreq computed from each wrapper file — and are distinct (different
    # wrapper content → different file hashes), proving the sidecar identity is anchored, not
    # a self-reported claim a changed wrapper could forge.
    assert hashes == {_file_sha256(wrapper_a), _file_sha256(wrapper_b)}
    assert len(hashes) == 2
    for cp in candidate_provs:
        assert cp.get("client_kind") == "cli"
        assert cp.get("prompt_version") == _DECOMPOSITION_PROMPT_VERSION
        assert cp.get("source") == "cli_decomposition"


def test_cli_audit_scheme_runs_cross_provider_audit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Work Item 3: ``--audit-client cli:<wrapper>`` runs a cross-provider audit.

    Two cli decomposition echo wrappers form the ensemble (≥2 clients triggers the
    ensemble + audit path); the audit echo wrapper returns a passing JSON verdict. The
    report's ``ensemble_candidate_audit_verdicts`` carry the audit sidecar's resolved
    model id, proving the audit transport records WHICH provider audited (the
    cross-provider diversity the scope's audit policy wants) — no longer a refusal.
    """
    _clear_model_env(monkeypatch)
    audit_json = json.dumps(
        {"covers_all_clauses": True, "invented_premises": [], "verdict": "passed"}
    )
    audit_wrapper = _make_echo_wrapper(
        tmp_path, name="echo-audit", model="audit-model-snap",
        wrapper_name="run-audit", output_text=audit_json,
    )
    decomp_a = _make_echo_wrapper(
        tmp_path, name="echo-da", provider="alpha", model="alpha-snap",
        wrapper_name="run-alpha",
    )
    decomp_b = _make_echo_wrapper(
        tmp_path, name="echo-db", provider="beta", model="beta-snap",
        wrapper_name="run-beta",
    )
    req = tmp_path / "req.nlreq"
    req.write_text(_CONTROLLED)
    out = tmp_path / "report.json"

    exit_code = main([
        "semantic-translate", str(req),
        "--requirement-id", "R-AUD",
        "--title", "audit-cli",
        "--ensemble-client", f"cli:{decomp_a}",
        "--ensemble-client", f"cli:{decomp_b}",
        "--audit-client", f"cli:{audit_wrapper}",
        "--out", str(out),
    ])
    assert exit_code in (0, 1), f"expected 0/1 (agreement, audited), got {exit_code}"
    report = json.loads(out.read_text())
    verdicts = report.get("ensemble_candidate_audit_verdicts", [])
    assert len(verdicts) == 2, f"expected 2 audit verdicts, got {len(verdicts)}"
    for v in verdicts:
        assert v is not None
        assert v["verdict"] == "passed"
        # The audit verdict records the audit sidecar's resolved model id (not a tier).
        assert v["model_id"] == "audit-model-snap"


# ---------------------------------------------------------------------------
# Drafting CLI transport stamps sidecar provenance (acceptance #4)
# ---------------------------------------------------------------------------


def test_cli_intake_draft_stamps_sidecar_provenance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Acceptance #4: ``intake-draft`` via the cli transport stamps the sidecar-resolved
    model / provider / route / wrapper / wrapper_hash into the proposal metadata.

    The ``LlmClient`` protocol returns only text, so the validated sidecar would otherwise
    be lost; the CLI merges ``CliLlmClient.last_call_provenance()`` into the proposal's
    producer metadata after a successful call. Provenance records the sidecar-resolved
    model id, NOT the tier (scope §4). Default/anthropic/recorded paths are untouched.
    """
    _clear_model_env(monkeypatch)
    wrapper = _make_echo_wrapper(
        tmp_path, name="echo-draft", provider="echo-provider", model="echo-draft-snap",
        wrapper_name="run-echo",
    )
    cfg = tmp_path / "cli-draft.toml"
    cfg.write_text("[drafting]\nclient = 'cli'\nwrapper = " + json.dumps(str(wrapper)) + "\n")
    prose = tmp_path / "prose.txt"
    prose.write_text("An unauthorized actor must be blocked before any state change.")
    out = tmp_path / "proposal.json"

    exit_code = main([
        "intake-draft", str(prose),
        "--method", "llm",
        "--model-config", str(cfg),
        "--intake-id", "INTAKE-D",
        "--proposal-id", "PROP-D",
        "--out", str(out),
    ])
    assert exit_code == 0
    proposal = json.loads(out.read_text())
    # The sidecar-resolved model id is the authoritative producer.model (the factory could not
    # know it at construction time) — NOT the tier (scope §4).
    assert proposal["producer"]["model"] == "echo-draft-snap"
    md = proposal["producer"]["metadata"]
    assert md["source_language"] == "en"
    assert md["client_kind"] == "cli"
    assert md["resolved_model"] == "echo-draft-snap"  # sidecar id, not a tier
    assert md["provider"] == "echo-provider"
    assert md["route"] == "official"
    assert md["wrapper"] == "run-echo"
    assert md["wrapper_hash"] == _file_sha256(wrapper)
    assert md["prompt_version"] == _DRAFTING_PROMPT_VERSION
    # Provenance records the sidecar-resolved model id, NEVER the tier (scope §4).
    assert "tier" not in md


# ---------------------------------------------------------------------------
# Per-call cli: scheme grammar: tier shorthand + model verification (explicit model=<id> OR
# bare <model-id>, the scope's cli:<wrapper>[:<tier-or-model>] form) + repeated-field rejection.
# iter-2: a bare <model-id> suffix is the model-verification guard, NOT an ambiguous refusal —
# the fail-closed sidecar refuses a mismatch, so a bare suffix can never silently mis-select
# (ADR 0204 §4.1). Provenance records the sidecar-resolved id, never the tier.
# ---------------------------------------------------------------------------


def test_cli_scheme_model_suffix_match_accepts_and_records_resolved_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``cli:<wrapper>:model=<id>`` pins the EXPECTED resolved model; when the sidecar reports the
    same id the call is accepted and provenance records that id (not the tier). The operator
    wrappers resolve models from wrapper+tier-specific env vars, so the per-call scheme cannot
    *pin* via env without wrapper-specific knowledge — ``model=`` is a verification guard the
    fail-closed sidecar enforces (scope §4)."""
    _clear_model_env(monkeypatch)
    wrapper = _make_echo_wrapper(tmp_path)  # sidecar resolved_model = echo-model-snapshot-20260601
    client = CliLlmClient(
        wrapper=str(wrapper), role=Role.drafting, model_env={"ECHO_MODE": "ok"},
        timeout_s=30.0, expected_resolved_model="echo-model-snapshot-20260601",
    )
    text = client.propose_controlled_rewrite("prose", "grammar")
    assert text == _CANNED_COMPLETION
    prov = client.last_call_provenance()
    assert prov["resolved_model"] == "echo-model-snapshot-20260601"  # sidecar id, not a tier
    assert "tier" not in prov


def test_cli_scheme_model_suffix_mismatch_refuses(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """``cli:<wrapper>:model=<id>`` with a sidecar that resolved a DIFFERENT model refuses — a
    wrapper that answered with a model other than the one the per-call scheme required is a
    provenance hazard (the recorded model would not match the requested one)."""
    _clear_model_env(monkeypatch)
    wrapper = _make_echo_wrapper(tmp_path)  # sidecar resolved_model = echo-model-snapshot-20260601
    client = CliLlmClient(
        wrapper=str(wrapper), role=Role.drafting, model_env={"ECHO_MODE": "ok"},
        timeout_s=30.0, expected_resolved_model="a-different-model-id",
    )
    with pytest.raises(CliTransportError, match="resolved model mismatch"):
        client.propose_controlled_rewrite("prose", "grammar")


def test_cli_scheme_tier_shorthand_and_prefix_parse(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """The ``cli:`` suffix grammar parses bare tier shorthand (``cli:w:2``, spelled ``cli:w:tier-2``)
    and explicit ``tier=<t>`` (1|2|3|4|5, or ``tier-N``) into the client's ``--tier``;
    ``model=<id>`` AND a bare ``<model-id>`` (the scope's ``cli:<wrapper>[:<tier-or-model>]``
    form) both parse into the expected-resolved-model verification guard, in any order relative
    to a tier (iter-2 fix). The spelled ``tier-N`` form is canonicalized to the bare digit —
    the same prefix-stripping the operator wrappers do."""
    from nlreq.cli import _resolve_client_scheme
    from nlreq.model_config import ModelConfig

    _clear_model_env(monkeypatch)
    cfg = ModelConfig()
    for spec, expect_tier, expect_model in [
        ("cli:run-gpt", None, None),
        ("cli:run-gpt:2", "2", None),
        ("cli:run-gpt:tier-2", "2", None),  # spelled form → canonical digit
        ("cli:run-gpt:tier=3", "3", None),
        ("cli:run-gpt:tier=tier-3", "3", None),  # spelled form in the explicit prefix
        ("cli:run-gpt:model=gpt-4o-mini", None, "gpt-4o-mini"),
        ("cli:run-gpt:tier=1:model=gpt-5.5", "1", "gpt-5.5"),
        # iter-2: a bare <model-id> suffix is the model-verification guard (NOT an ambiguous refusal).
        ("cli:run-gpt:gpt-5.4-mini", None, "gpt-5.4-mini"),
        ("cli:run-gpt:1:gpt-5.5", "1", "gpt-5.5"),  # tier shorthand + bare model
        ("cli:run-gpt:gpt-5.5:1", "1", "gpt-5.5"),  # bare model + tier (any order)
    ]:
        built = _resolve_client_scheme(spec, Role.drafting, cfg)
        assert built.client._tier == expect_tier, spec
        assert built.client._expected_resolved_model == expect_model, spec


def test_cli_scheme_bare_model_suffix_is_verification_guard(monkeypatch: pytest.MonkeyPatch) -> None:
    """A bare ``cli:<wrapper>:<model-id>`` suffix (the scope's ``cli:<wrapper>[:<tier-or-model>]``
    grammar) is the model-id VERIFICATION guard — the same fail-closed sidecar check as
    ``model=<id>`` — NOT an ambiguous refusal (iter-2 fix). A bare suffix reaching the parser is
    by construction not a tier (all-digit/tier-N shorthand is matched first, and the legacy tier
    names are rejected outright), so the only remaining interpretation is a model id; the
    fail-closed sidecar refuses if the wrapper resolved a different model (ADR 0204 §4.1).
    ``model=<id>`` remains the explicit form."""
    from nlreq.cli import _resolve_client_scheme
    from nlreq.model_config import ModelConfig

    _clear_model_env(monkeypatch)
    cfg = ModelConfig()
    for spec, expect_model in [
        ("cli:run-gpt:gpt-5.4-mini", "gpt-5.4-mini"),
        ("cli:run-gpt:bogus-model-id", "bogus-model-id"),
        # A mis-typed tier prefix ("ter-2" is not "tier-2") contains non-digits, so it is the
        # model-verification guard — the fail-closed sidecar refuses it at call time.
        ("cli:run-gpt:ter-2", "ter-2"),
    ]:
        built = _resolve_client_scheme(spec, Role.drafting, cfg)
        assert built.client._expected_resolved_model == expect_model, spec
        assert built.client._tier is None, spec


def test_cli_scheme_legacy_tier_names_rejected_with_migration_hint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The legacy tier names (heavy|lite|tiny) are rejected in tier position — bare, ``tier=``,
    or ``tier-`` spelled — with the wrappers' migration hint, NEVER silently reinterpreted as
    the model-id verification guard (that would send the call through with a claimed tier the
    wrapper no longer understands, or worse, treat the tier name as an expected model id)."""
    from nlreq.cli import _resolve_client_scheme
    from nlreq.model_config import ModelConfig, ModelConfigError

    _clear_model_env(monkeypatch)
    cfg = ModelConfig()
    for spec in (
        "cli:run-claude:heavy",
        "cli:run-gpt:lite",
        "cli:run-gpt:tiny",
        "cli:run-gpt:tier=heavy",
        "cli:run-gpt:tier-lite",
    ):
        with pytest.raises(
            ModelConfigError,
            match=r"was renamed — tiers are now 1\.\.5 \(heavy→1, lite→2, tiny→3\)",
        ):
            _resolve_client_scheme(spec, Role.drafting, cfg)


def test_cli_scheme_out_of_range_numeric_tier_refuses(monkeypatch: pytest.MonkeyPatch) -> None:
    """An all-digit bare suffix is ALWAYS tier position (a real model id contains a non-digit
    character), so an out-of-range number is an unknown-tier refusal — never a silent fall-through
    to the model-verification guard."""
    from nlreq.cli import _resolve_client_scheme
    from nlreq.model_config import ModelConfig, ModelConfigError

    _clear_model_env(monkeypatch)
    cfg = ModelConfig()
    for spec in ("cli:run-gpt:6", "cli:run-gpt:0", "cli:run-gpt:tier=12"):
        with pytest.raises(
            ModelConfigError, match=r"unknown tier '\d+' \(use 1\|2\|3\|4\|5\)"
        ):
            _resolve_client_scheme(spec, Role.drafting, cfg)


def test_cli_scheme_repeated_model_suffix_refuses(monkeypatch: pytest.MonkeyPatch) -> None:
    """Specifying the model MORE THAN ONCE — two bare model ids, or ``model=<id>`` plus a bare
    model id (in either order) — is a structured refusal: a per-call scheme must assert exactly
    one expected model (iter-2 fix). The bare suffix is the verification guard, so the
    duplicate-model guard is what catches a malformed scheme now that bare suffixes are accepted."""
    from nlreq.cli import _resolve_client_scheme
    from nlreq.model_config import ModelConfig, ModelConfigError

    _clear_model_env(monkeypatch)
    cfg = ModelConfig()
    for bad in (
        "cli:run-gpt:alpha:beta",              # two bare model ids
        "cli:run-gpt:model=alpha:beta",        # model= then bare
        "cli:run-gpt:alpha:model=alpha",       # bare then model=
    ):
        with pytest.raises(ModelConfigError, match="specifies model more than once"):
            _resolve_client_scheme(bad, Role.drafting, cfg)


def test_cli_scheme_bad_tier_value_refuses(monkeypatch: pytest.MonkeyPatch) -> None:
    """``tier=<not-a-tier>`` is rejected — the explicit tier form validates 1|2|3|4|5."""
    from nlreq.cli import _resolve_client_scheme
    from nlreq.model_config import ModelConfig, ModelConfigError

    _clear_model_env(monkeypatch)
    with pytest.raises(
        ModelConfigError, match=r"unknown tier 'medium' \(use 1\|2\|3\|4\|5\)"
    ):
        _resolve_client_scheme("cli:run-gpt:tier=medium", Role.drafting, ModelConfig())


def test_cli_ensemble_model_suffix_records_sidecar_resolved_model_not_tier(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A decomposition ensemble ``cli:<wrapper>:model=<id>`` records the sidecar-resolved model id
    (which MUST equal the pinned id) in the report — never the tier (scope §4, recommended action #6).

    The echo wrapper's sidecar reports ``alpha-model-snap``; the ``model=alpha-model-snap`` suffix
    pins that exact id, so the call is accepted and the candidate provenance records it.
    """
    _clear_model_env(monkeypatch)
    wrapper_a = _make_echo_wrapper(
        tmp_path, name="echo-a", provider="alpha-provider", model="alpha-model-snap",
        wrapper_name="run-alpha",
    )
    wrapper_b = _make_echo_wrapper(
        tmp_path, name="echo-b", provider="beta-provider", model="beta-model-snap",
        wrapper_name="run-beta",
    )
    req = tmp_path / "req.nlreq"
    req.write_text(_CONTROLLED)
    out = tmp_path / "report.json"

    exit_code = main([
        "semantic-translate", str(req),
        "--requirement-id", "R-MDLOVR",
        "--title", "model-override",
        # Both clients pin their EXPECTED resolved model via model=<id>; the fail-closed sidecar
        # check verifies each wrapper resolved exactly that id (scope §4).
        "--ensemble-client", f"cli:{wrapper_a}:model=alpha-model-snap",
        "--ensemble-client", f"cli:{wrapper_b}:model=beta-model-snap",
        "--out", str(out),
    ])
    assert exit_code in (0, 1)
    report = json.loads(out.read_text())
    cps = report["ensemble_candidate_provenances"]
    assert len(cps) == 2
    models = {cp["model"] for cp in cps}
    assert models == {"alpha-model-snap", "beta-model-snap"}  # sidecar-resolved ids, not tiers
    for cp in cps:
        assert cp["client_kind"] == "cli"
        assert "tier" not in cp  # never the tier


# ---------------------------------------------------------------------------
# Impact CLI transport stamps sidecar provenance (acceptance #4)
# ---------------------------------------------------------------------------


def test_cli_python_source_impact_production_llm_client_stamps_provenance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Acceptance #4: ``python-source-impact-production --llm-client cli:<wrapper>`` runs a
    cross-provider semantic impact estimate and stamps the sidecar-resolved model / provider /
    wrapper / wrapper_hash / prompt_version into the report metadata.

    The LLM estimate is non-gateable review input (PC-9): it cross-validates against the
    deterministic call graph but never becomes gateable on its own. The echo wrapper returns a
    JSON array of impacted module ids + a valid sidecar.
    """
    _clear_model_env(monkeypatch)
    src = tmp_path / "src"
    src.mkdir()
    (src / "auth.py").write_text(
        "from state import state_change\n\ndef operation(actor):\n    return state_change()\n"
    )
    (src / "state.py").write_text("def state_change():\n    return 'changed'\n")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({
        "schema_version": "0.1", "adapter": "python-source", "language": "python", "runtime": "cpython",
        "modules": [
            {"module_id": "auth", "path": "src/auth.py", "symbols": ["operation"]},
            {"module_id": "state", "path": "src/state.py", "symbols": ["state_change"]},
        ],
    }))
    estimate = json.dumps(["auth"])
    wrapper = _make_echo_wrapper(
        tmp_path, name="echo-impact", model="impact-model-snap",
        wrapper_name="run-impact", output_text=estimate,
    )
    out = tmp_path / "report.json"

    exit_code = main([
        "python-source-impact-production",
        "--manifest", str(manifest),
        "--symbol", "operation",
        "--llm-client", f"cli:{wrapper}",
        "--prose", "Unauthorized actors must be blocked before any state change.",
        "--project-root", str(tmp_path),
        "--out", str(out),
    ])
    assert exit_code == 0
    report = json.loads(out.read_text())
    md = report["metadata"]
    assert md["mode"] == "production_source_impact_v2"  # original metadata preserved
    assert md["client_kind"] == "cli"
    assert md["resolved_model"] == "impact-model-snap"  # sidecar id, not a tier
    assert md["provider"] == "echo"
    assert md["route"] == "official"
    assert md["wrapper"] == "run-impact"
    assert md["wrapper_hash"] == _file_sha256(wrapper)
    assert md["prompt_version"] == _IMPACT_PROMPT_VERSION
    assert "tier" not in md
    # The LLM estimate named "auth" as a non-gateable semantic suggestion (PC-9).
    assert any(
        s["module_id"] == "auth" and s["source"] == "llm"
        for s in report["semantic_suggestions"]
    )


# ---------------------------------------------------------------------------
# Calibration report is self-describing for the cli transport (recommended action #2)
# ---------------------------------------------------------------------------


def test_benchmark_translation_cli_calibration_report_is_self_describing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``benchmark-translation --run --llm-client cli:<wrapper>`` stamps a self-describing
    ``calibration`` block — role / client_kind / provider / resolved_model / wrapper /
    wrapper_hash / route / cli_version / prompt_version — from the validated sidecar, so the
    FA/FR tables record WHICH provider/model answered under which wrapper identity (scope §5).
    Provenance records the sidecar-resolved model id, NEVER the tier (scope §4)."""
    from nlreq.translation_benchmark import (
        RequirementTranslationCase,
        RequirementTranslationCorpus,
        RequirementTranslationExpected,
    )

    _clear_model_env(monkeypatch)
    wrapper = _make_echo_wrapper(
        tmp_path, name="echo-calib", provider="echo-provider", model="calib-model-snap",
        wrapper_name="run-calib",
    )
    # A one-case corpus: the echo wrapper returns _CANNED_COMPLETION regardless of input, so the
    # FA/FR value is irrelevant — this test asserts the calibration PROVENANCE, not the rates.
    corpus = RequirementTranslationCorpus(
        corpus_id="calib-cli", version="0.1",
        cases=[RequirementTranslationCase(
            case_id="c1", title="t", input_text="Reject an unauthorized withdrawal.",
            input_kind="messy_prose", domain="d", language="en",
            gold_controlled_text=_CANNED_COMPLETION,
            recorded_controlled_text=_CANNED_COMPLETION,
            expected=RequirementTranslationExpected(outcome="accepted"),  # type: ignore[arg-type]
        )],
    )
    corpus_path = tmp_path / "corpus.json"
    corpus_path.write_text(corpus.model_dump_json())
    out = tmp_path / "report.json"

    exit_code = main([
        "benchmark-translation",
        "--corpus", str(corpus_path),
        "--run",
        "--llm-client", f"cli:{wrapper}",
        "--out", str(out),
    ])
    assert exit_code in (0, 1)
    report = json.loads(out.read_text())
    cal = report["calibration"]
    assert cal["role"] == "drafting"
    assert cal["client_kind"] == "cli"
    assert cal["provider"] == "echo-provider"
    assert cal["resolved_model"] == "calib-model-snap"  # sidecar id, not a tier
    assert cal["wrapper"] == "run-calib"
    assert cal["wrapper_hash"] == _file_sha256(wrapper)
    assert cal["route"] == "official"
    assert cal["cli_version"] == "echo-1.0"
    assert cal["prompt_version"] == _DRAFTING_PROMPT_VERSION
    assert cal["transport_source"] == "override"
    assert "tier" not in cal  # never the tier


def test_model_env_exports_are_the_pinning_mechanism_and_profile_wins(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The config/env ``model_env`` rung is the model-PINNING mechanism (scope §4): explicit
    model-env exports are added to the wrapper's environment, winning over the wrapper's
    ``models.env`` defaults (conditional-assignment → process env wins). The per-call
    ``cli:<wrapper>:model=<id>`` scheme is verification-only BY DESIGN (ADR 0203) — it cannot
    pin without wrapper-specific env-var knowledge, so pinning is ``model_env``'s job.

    The pure-completion profile (``OSS_SOFT_FALLBACK=0`` / ``PI_TOOLS=""``) is applied AFTER
    ``model_env`` so a misconfigured ``model_env`` cannot defeat the no-tools/no-fallback
    contract — the profile is non-negotiable (defence in depth; the sidecar is the real guard)."""
    _clear_model_env(monkeypatch)
    client = CliLlmClient(
        wrapper="run-claude",
        role=Role.drafting,
        model_env={
            "CLAUDE_TIER3_MODEL": "claude-haiku-4-5-20251001",  # a model-pinning export
            # A hostile/misconfigured model_env trying to defeat the pure-completion profile:
            "OSS_SOFT_FALLBACK": "1",
            "PI_TOOLS": "read,bash",
        },
        timeout_s=5.0,
    )
    env = client._build_env()
    # The model-pinning export reaches the wrapper env (wins over models.env defaults).
    assert env["CLAUDE_TIER3_MODEL"] == "claude-haiku-4-5-20251001"
    # The pure-completion profile WINS over the hostile model_env — non-negotiable.
    assert env["OSS_SOFT_FALLBACK"] == "0"
    assert env["PI_TOOLS"] == ""


def test_per_call_model_suffix_is_verification_only_by_design(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The per-call ``cli:<wrapper>:model=<id>`` suffix is a VERIFICATION guard, not model
    selection: it cannot pin the model (the operator wrappers resolve models from
    wrapper+tier-specific env vars, so per-call pinning needs wrapper-specific knowledge that is
    ``model_env``'s job). It asserts exactly which model answered — the fail-closed sidecar
    refuses if the wrapper resolved a different model (ADR 0203 / scope §4)."""
    _clear_model_env(monkeypatch)
    # The echo wrapper's sidecar reports resolved_model = echo-model-snapshot-20260601.
    wrapper = _make_echo_wrapper(tmp_path)
    # model=<id> matching the sidecar → accepted (verification passes).
    client_ok = CliLlmClient(
        wrapper=str(wrapper), role=Role.drafting, model_env={"ECHO_MODE": "ok"},
        timeout_s=30.0, expected_resolved_model="echo-model-snapshot-20260601",
    )
    assert client_ok.propose_controlled_rewrite("prose", "grammar") == _CANNED_COMPLETION
    assert client_ok.last_call_provenance()["resolved_model"] == "echo-model-snapshot-20260601"
    # model=<id> NOT matching the sidecar → refused (verification fails). Already covered by
    # test_cli_scheme_model_suffix_mismatch_refuses; this test documents the by-design split:
    # selection = model_env (config/env rung); verification = model= (per-call scheme).


# ---------------------------------------------------------------------------
# Committed real cross-provider ensemble evidence (acceptance #2, ADR 0204 §5)
# ---------------------------------------------------------------------------
_ENSEMBLE_EVIDENCE_DIR = Path(__file__).resolve().parents[1] / "benchmarks" / "cross-provider-ensemble"
_ENSEMBLE_EVIDENCE_REPORTS = {
    "20260625134538-cross-provider-ensemble-run-claude-run-gpt.json",
}


def test_committed_cross_provider_ensemble_evidence_records_two_distinct_providers() -> None:
    """The committed real two-provider ensemble report is the durable acceptance-#2 artifact
    (ADR 0204 §5: the real ``cli:run-claude`` + ``cli:run-gpt`` package, produced once the
    operator landed §6). It round-trips through ``SemanticTranslationReport`` and its
    ``ensemble_candidate_provenances`` record TWO DISTINCT providers (anthropic + openai),
    resolved model ids, wrapper hashes, and prompt versions — the cross-provider diversity an
    agreement gate exists to catch. Both candidates are unaudited (CliLlmClient always produces
    is_audited=False) so the result is needs_review; the diversity is recorded regardless.

    Structural invariants are the durable contract (live model text is not byte-reproducible);
    update this test + ADR 0204 §5 only if the ensemble evidence is regenerated.
    """
    from nlreq.semantic_translation import SemanticTranslationReport

    assert sorted(p.name for p in _ENSEMBLE_EVIDENCE_DIR.glob("*.json")) == sorted(_ENSEMBLE_EVIDENCE_REPORTS), (
        "cross-provider ensemble evidence set drifted; update this test and ADR 0204 §5"
    )
    name = next(iter(_ENSEMBLE_EVIDENCE_REPORTS))
    report = SemanticTranslationReport.model_validate_json(
        (_ENSEMBLE_EVIDENCE_DIR / name).read_text()
    )
    cps = report.ensemble_candidate_provenances
    assert len(cps) == 2, f"expected 2 candidates, got {len(cps)}"
    providers = {cp.get("provider") for cp in cps}
    assert providers == {"anthropic", "openai"}, providers  # two DISTINCT providers
    assert len({cp.get("model") for cp in cps}) == 2  # two distinct resolved model ids
    wrappers = {cp.get("wrapper") for cp in cps}
    assert wrappers == {"run-claude", "run-gpt"}, wrappers
    assert len({cp.get("wrapper_hash") for cp in cps}) == 2  # two distinct wrapper hashes
    for cp in cps:
        assert cp.get("client_kind") == "cli"
        assert cp.get("prompt_version") == _DECOMPOSITION_PROMPT_VERSION
    # Both candidates unaudited → needs_review (the honest trust-check state; the diversity is
    # recorded before the trust check). Update only if the evidence is regenerated with audit.
    assert report.result == "needs_review", f"expected needs_review, got {report.result!r}"


# ---------------------------------------------------------------------------
# Real-wrapper tests (skip unless explicitly opted in — not CI-safe)
# ---------------------------------------------------------------------------
#
# These exercise the REAL operator wrappers (run-claude / run-gpt) end-to-end through
# CliLlmClient. They require (a) operator provider auth and (b) the §6-eligible wrappers that
# emit <output>.meta.json under the pure-completion profile (scope §6 / ADR 0203 / ADR 0204 §5).
# Both landed 2026-06-25, so these now assert ROUND-TRIPS (the prior refusal test is flipped).
# Opt in with NLREQ_RUN_REAL_WRAPPER_TESTS=1; they cost real API calls and are not CI-safe.


_REAL_SKIP_REASON = (
    "real-wrapper tests need operator auth + the §6-eligible operator wrappers; "
    "run manually with NLREQ_RUN_REAL_WRAPPER_TESTS=1"
)


def _real_wrapper_path(name: str) -> str | None:
    """Resolve a real operator wrapper: PATH first, then the operator's conventional bin dir.

    The wrappers are operator-private (not shipped, ADR 0202), so this resolves ``name`` on PATH
    first and falls back to ``$HOME/Documents/GitHub/.claude/bin/<name>`` (the operator's
    conventional location); returns None (→ skip) when absent so the tests stay portable.
    """
    import shutil

    found = shutil.which(name)
    if found:
        return found
    default = Path.home() / "Documents" / "GitHub" / ".claude" / "bin" / name
    return str(default) if default.is_file() else None


@pytest.mark.skipif(os.environ.get("NLREQ_RUN_REAL_WRAPPER_TESTS") != "1", reason=_REAL_SKIP_REASON)
def test_real_run_claude_wrapper_round_trip() -> None:
    """A real ``run-claude`` wrapper (§6-eligible) round-trips: the call succeeds and provenance
    records the sidecar-resolved model / provider / wrapper identity (acceptance #2/#4 transport).

    The operator's run-claude emits ``<output>.meta.json`` (provider=anthropic, resolved_model,
    route=official, tools_active=false, wrapper_hash) under the pure-completion profile
    (``--bare --tools ""``: no tools — verified, a random-token file is not leaked — no
    CLAUDE.md/hooks context, API-key auth sourced from .env). This is the round-trip the prior
    refusal test said to flip to once §6 landed (ADR 0204 §5).
    """
    wrapper = _real_wrapper_path("run-claude")
    if wrapper is None:
        pytest.skip("run-claude wrapper not found (PATH or operator bin dir)")
    client = CliLlmClient(wrapper=wrapper, role=Role.drafting, tier="3", timeout_s=180.0)
    text = client.propose_controlled_rewrite(
        "An unauthorized actor must be blocked before any state change.",
        "grammar summary",
        language="en",
    )
    assert text, "expected a non-empty drafting completion"
    prov = client.last_call_provenance()
    assert prov["provider"] == "anthropic"
    assert prov["wrapper"] == "run-claude"
    assert prov["route"] == "official"  # no silent fallback
    assert prov["resolved_model"]  # sidecar-resolved id, NOT the tier (scope §4)
    assert prov["wrapper_hash"]
    assert prov["cli_version"]


@pytest.mark.skipif(os.environ.get("NLREQ_RUN_REAL_WRAPPER_TESTS") != "1", reason=_REAL_SKIP_REASON)
def test_real_run_gpt_wrapper_round_trip() -> None:
    """A real ``run-gpt`` wrapper (§6-eligible) round-trips with provider=openai — the SECOND
    distinct provider for the cross-provider ensemble (acceptance #2).

    Pure-completion profile: every tool-bearing codex feature disabled (shell_tool /
    unified_exec / browser_use / computer_use — verified, the model reports "no shell execution
    tool is available"), read-only sandbox (defence in depth), --ignore-rules/--ignore-user-config
    (no project/user context), scratch empty cwd (no AGENTS.md). tools_active=false is honest.
    """
    wrapper = _real_wrapper_path("run-gpt")
    if wrapper is None:
        pytest.skip("run-gpt wrapper not found (PATH or operator bin dir)")
    # low reasoning effort keeps the opt-in test fast; the transport contract is effort-independent.
    client = CliLlmClient(
        wrapper=wrapper, role=Role.drafting, tier="3", timeout_s=180.0,
        model_env={"GPT_REASONING_EFFORT": "low"},
    )
    text = client.propose_controlled_rewrite(
        "An unauthorized actor must be blocked before any state change.",
        "grammar summary",
        language="en",
    )
    assert text
    prov = client.last_call_provenance()
    assert prov["provider"] == "openai"
    assert prov["wrapper"] == "run-gpt"
    assert prov["route"] == "official"
    assert prov["resolved_model"]
    assert prov["wrapper_hash"]


@pytest.mark.skipif(os.environ.get("NLREQ_RUN_REAL_WRAPPER_TESTS") != "1", reason=_REAL_SKIP_REASON)
def test_real_cli_two_provider_ensemble_records_two_distinct_providers(tmp_path: Path) -> None:
    """Acceptance #2 (REAL): a ``cli:run-claude`` + ``cli:run-gpt`` decomposition ensemble
    produces a package whose ``ensemble_candidate_provenances`` records two DISTINCT providers
    (anthropic + openai), resolved model ids, wrapper hashes, and prompt versions.

    This is the real two-provider artifact ADR 0204 §5 said required the operator to land §6.
    Both candidates are unaudited (CliLlmClient always produces is_audited=False) so the result
    is needs_review (exit 1), but the candidate provenances are populated BEFORE the trust check
    — the cross-provider diversity is recorded regardless. (Live model output can occasionally
    fail to parse as DSL v3; this opt-in test then fails with exit 2 — a real signal about the
    models, not a transport regression.)
    """
    wclaude = _real_wrapper_path("run-claude")
    wgpt = _real_wrapper_path("run-gpt")
    if wclaude is None or wgpt is None:
        pytest.skip("run-claude/run-gpt wrappers not found (PATH or operator bin dir)")
    req = tmp_path / "req.nlreq"
    req.write_text(_CONTROLLED)
    out = tmp_path / "report.json"
    exit_code = main([
        "semantic-translate", str(req),
        "--requirement-id", "R-REAL-CP",
        "--title", "real-cross-provider",
        "--ensemble-client", f"cli:{wclaude}:3",
        "--ensemble-client", f"cli:{wgpt}:3",
        "--out", str(out),
    ])
    assert exit_code in (0, 1), f"expected 0/1 (agreement/needs-review), got {exit_code}"
    report = json.loads(out.read_text())
    cps = report["ensemble_candidate_provenances"]
    assert len(cps) == 2, f"expected 2 candidates, got {len(cps)}"
    providers = {cp["provider"] for cp in cps}
    assert providers == {"anthropic", "openai"}, providers  # two DISTINCT providers
    assert len({cp["model"] for cp in cps}) == 2  # two distinct resolved model ids
    assert {cp["wrapper"] for cp in cps} == {"run-claude", "run-gpt"}
    assert len({cp["wrapper_hash"] for cp in cps}) == 2  # two distinct wrapper hashes
    for cp in cps:
        assert cp["client_kind"] == "cli"
        assert cp["prompt_version"] == _DECOMPOSITION_PROMPT_VERSION


# ---------------------------------------------------------------------------
# Ineligible-wrapper refusal tests (skipif the wrapper is absent — CI-safe)
# ---------------------------------------------------------------------------
#
# ADR 0204 §5 marks run-oss / run-oss-local / run-gemini attestation-INELIGIBLE: each
# lacks a real no-tools/no-context pure-completion knob, so under NLREQ_ATTESTATION=1 they
# REFUSE UPFRONT (exit 2, clear stderr, ZERO egress — no model call, no sidecar, no output
# file). nlreq's CliLlmClient sees the non-zero exit and raises CliTransportError (a
# structured refusal, acceptance #3). These tests empirically verify that eligibility
# claim: an ineligible wrapper can never produce an accepted draft.
#
# They are NOT opt-in (unlike the eligible-wrapper round-trips above): the refusal happens
# BEFORE any model call (zero egress, no cost), so they are safe to run whenever the
# operator wrapper is present. They skip only when the wrapper is absent (CI, where the
# operator-private wrappers are not installed) — the same skipif-absent pattern as the
# apalache/forge/go real-run tests.


@pytest.mark.parametrize("wrapper_name", ["run-oss", "run-oss-local", "run-gemini"])
def test_ineligible_wrapper_refuses_upfront_with_zero_egress(wrapper_name: str) -> None:
    """An attestation-INELIGIBLE wrapper (ADR 0204 §5) refuses upfront under NLREQ_ATTESTATION=1,
    and CliLlmClient surfaces that as a CliTransportError — never an accepted draft (acceptance #3).

    run-oss / run-oss-local are pi-based (pi requires >=1 tool per request, so the no-tools
    pure-completion contract cannot be honored); run-gemini is agentic with no verified
    no-tools/no-context knob. Each exits 2 BEFORE any model call (zero egress — no sidecar,
    no output file), so this is safe to run whenever the wrapper is present (not opt-in). The
    wrapper's stderr is captured into the CliTransportError message; asserting it names the
    attestation refusal confirms the exit is the documented ineligibility guard (ADR 0204 §5),
    not an unrelated wrapper/transport failure.
    """
    wrapper = _real_wrapper_path(wrapper_name)
    if wrapper is None:
        pytest.skip(f"{wrapper_name} wrapper not found (PATH or operator bin dir)")
    client = CliLlmClient(wrapper=wrapper, role=Role.drafting, tier="3", timeout_s=30.0)
    with pytest.raises(CliTransportError) as exc_info:
        client.propose_controlled_rewrite(
            "An unauthorized actor must be blocked before any state change.",
            "grammar summary",
            language="en",
        )
    msg = str(exc_info.value)
    # The upfront refusal exits 2 (not a timeout, not a sidecar violation — those are the
    # eligible-wrapper failure modes). Asserting exit 2 + the attestation-refusal stderr
    # confirms this is the documented ineligibility guard, not an unrelated error.
    assert "exited 2" in msg, f"expected exit 2 (upfront refusal), got: {msg!r}"
    assert "attestation" in msg.lower() or "refused" in msg.lower(), (
        f"expected an attestation-refusal message, got: {msg!r}"
    )


# ---------------------------------------------------------------------------
# CLI-level attest-spec machine-pin (three-zone scope §7; HELPER iter-3 #1).
#
# The library-level tests (test_attest_spec.py) prove the orchestrator machine-pins given a real
# shape check; THESE tests prove the whole PRODUCTION CLI path — argv → per-role client resolution
# → provider-family derivation (run-claude→anthropic / run-gpt→openai) → the REAL
# ``deterministic_shape_for_controlled_text`` (NOT a test-injected check) → route_machine_pinning →
# the written report — actually auto-advances a clean cross-provider-agreed candidate end-to-end.
# This closes the iter-3 gap where the CLI never supplied a shape check, so only library tests
# could auto-advance (the production command could never machine-pin).
# ---------------------------------------------------------------------------


# A controlled requirement the REAL deterministic shape check parses + binds + evidences (the
# authorization_precondition fixture shape); both drafting wrappers echo it so the ensemble agrees.
_ATTEST_PARSEABLE_CONTROLLED = (
    "For every operation request:\n"
    "  if actor is not authorized\n"
    "  then operation must be rejected before state_change.\n"
)


def _write_machine_pin_policy(tmp_path: Path) -> Path:
    """Write an opt-in machine-pin policy JSON (calibration + default-deny allow-list).

    The calibration covers the 2-member / 2-family / FA=0 configuration the echo ensemble produces,
    so the calibration-derived threshold admits it (AC9, no hand-set constant). The changed-path
    policy is enabled with a ``src/**`` allow-list, so a ``src/*`` changed path is admitted
    (default-deny, AC4). ``required_deterministic_levels`` is empty: machine pinning never
    substitutes for a proof level, and this CLI test exercises the routing/provenance path, not the
    evidence-level gate (which has its own library coverage).
    """
    policy = {
        "policy_id": "attest-cli-test",
        "schema_version": "0.1",
        "rules": {
            "minimum_ensemble_size": 2,
            "required_distinct_provider_families": 2,
            "required_deterministic_levels": [],
            "calibration": {
                "calibration_id": "ens-fa-cli-1",
                "configurations": [
                    {
                        "ensemble_size": 2,
                        "distinct_provider_families": 2,
                        "false_acceptance_rate": 0.0,
                        "sample_count": 50,
                    }
                ],
            },
            "changed_path_policy": {
                "enabled": True,
                "allowed_changed_path_patterns": ["src/**"],
            },
        },
    }
    path = tmp_path / "machine-pin-policy.json"
    path.write_text(json.dumps(policy), encoding="utf-8")
    return path


def _attest_drafting_wrappers(tmp_path: Path) -> tuple[Path, Path]:
    """Two cross-provider drafting wrappers (run-claude→anthropic, run-gpt→openai) that AGREE.

    The wrapper BASENAME drives ``provider_family`` (``PROVIDER_FAMILY_BY_WRAPPER``), so naming the
    files ``run-claude`` / ``run-gpt`` yields two distinct families that satisfy the diversity gate;
    both echo the SAME parseable controlled text so the drafting ensemble agrees.
    """
    wrapper_claude = _make_echo_wrapper(
        tmp_path, name="run-claude", provider="anthropic", model="claude-snap",
        wrapper_name="run-claude", output_text=_ATTEST_PARSEABLE_CONTROLLED,
    )
    wrapper_gpt = _make_echo_wrapper(
        tmp_path, name="run-gpt", provider="openai", model="gpt-snap",
        wrapper_name="run-gpt", output_text=_ATTEST_PARSEABLE_CONTROLLED,
    )
    return wrapper_claude, wrapper_gpt


def _attest_partition_wrappers(tmp_path: Path) -> tuple[Path, Path]:
    """Two cross-provider PARTITION wrappers (Zone 1) that AGREE on one candidate rule per segment.

    Mirrors ``_attest_drafting_wrappers`` for the partition role: the wrapper basenames
    (run-claude→anthropic, run-gpt→openai) give two distinct provider families, so the partition
    ensemble satisfies the ≥2-distinct-family diversity gate a machine pin requires (scope §4) — the
    rule's BOUNDARY, not just its wording, is cross-checked. Both echo the SAME candidate-rule JSON
    proposal, so the ensemble agrees with no boundary disagreement. Written into a ``partition``
    subdir so the basenames match the family table while the file paths stay distinct from the
    drafting wrappers.
    """
    proposal = json.dumps([{"rule": "The system shall reject unauthorized transfers."}])
    subdir = tmp_path / "partition"
    subdir.mkdir(exist_ok=True)
    wrapper_claude = _make_echo_wrapper(
        subdir, name="run-claude", provider="anthropic", model="claude-snap",
        wrapper_name="run-claude", output_text=proposal,
    )
    wrapper_gpt = _make_echo_wrapper(
        subdir, name="run-gpt", provider="openai", model="gpt-snap",
        wrapper_name="run-gpt", output_text=proposal,
    )
    return wrapper_claude, wrapper_gpt


def test_cli_attest_spec_machine_pins_a_clean_cross_provider_agreed_candidate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The production ``attest-spec`` CLI machine-pins a clean candidate end-to-end (HELPER iter-3 #1).

    Two cross-provider drafting wrappers echo the SAME parseable controlled text → the drafting
    ensemble agrees; the policy opts in with a calibration covering the 2-family configuration and a
    ``src/**`` allow-list; the changed path is ``src/*``. The CLI supplies the REAL
    ``deterministic_shape_for_controlled_text`` (no injected check), so this exercises the whole
    production path. The written report carries one ``machine_agreement`` pin whose ensemble records
    the two DISTINCT provider families the CLI derived from the wrapper basenames.
    """
    _clear_model_env(monkeypatch)
    monkeypatch.delenv("NLREQ_MACHINE_PIN", raising=False)
    wrapper_claude, wrapper_gpt = _attest_drafting_wrappers(tmp_path)
    # A machine pin also requires a cross-provider PARTITION ensemble (scope §4): the rule's boundary
    # must be cross-checked, not only its wording. Supply two distinct-family partition wrappers.
    partition_claude, partition_gpt = _attest_partition_wrappers(tmp_path)
    document = tmp_path / "spec.md"
    document.write_text("# Payments\n\nThe system shall reject unauthorized transfers.\n")
    policy = _write_machine_pin_policy(tmp_path)
    out = tmp_path / "attest-report.json"

    exit_code = main([
        "attest-spec", str(document),
        "--client", f"cli:{partition_claude}",
        "--client", f"cli:{partition_gpt}",
        "--draft-client", f"cli:{wrapper_claude}",
        "--draft-client", f"cli:{wrapper_gpt}",
        "--machine-pin-policy", str(policy),
        "--changed-path", "src/payments.py",
        "--out", str(out),
    ])
    assert exit_code == 0
    report = json.loads(out.read_text())

    # The production CLI path machine-pinned the clean cross-provider-agreed candidate.
    assert report["policy_off"] is False
    assert len(report["machine_pinned"]) == 1
    pin = report["machine_pinned"][0]
    assert pin["controlled_text"] == _ATTEST_PARSEABLE_CONTROLLED
    pinning = pin["pinning"]
    assert pinning["kind"] == "machine_agreement"
    # The ensemble members carry the two DISTINCT provider families the CLI derived from the wrapper
    # basenames — proving the provider-family derivation flowed into routing (not a same-family pin).
    families = {m["provider_family"] for m in pinning["ensemble"]["members"]}
    assert families == {"anthropic", "openai"}
    # A machine-pinned candidate requires no human attention — its index is NOT in the human queue.
    pinned_index = pin["candidate_index"]
    assert all(item["candidate_index"] != pinned_index for item in report["human_queue"])


def test_cli_attest_spec_policy_off_routes_every_candidate_to_human(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With NO ``--machine-pin-policy`` (and ``NLREQ_MACHINE_PIN`` unset) the production CLI emits no
    pin and routes every candidate to the human queue — byte-identical to today (AC1).

    Same agreeing cross-provider ensemble + changed path as the machine-pin test; ONLY the policy is
    absent. The default posture must never auto-advance, so ``policy_off`` is True and
    ``machine_pinned`` is empty regardless of how clean the candidate is.
    """
    _clear_model_env(monkeypatch)
    monkeypatch.delenv("NLREQ_MACHINE_PIN", raising=False)
    wrapper_claude, wrapper_gpt = _attest_drafting_wrappers(tmp_path)
    document = tmp_path / "spec.md"
    document.write_text("# Payments\n\nThe system shall reject unauthorized transfers.\n")
    out = tmp_path / "attest-report.json"

    exit_code = main([
        "attest-spec", str(document),
        "--draft-client", f"cli:{wrapper_claude}",
        "--draft-client", f"cli:{wrapper_gpt}",
        # NO --machine-pin-policy: machine pinning is OFF by default.
        "--changed-path", "src/payments.py",
        "--out", str(out),
    ])
    assert exit_code == 0
    report = json.loads(out.read_text())
    assert report["policy_off"] is True
    assert report["machine_pinned"] == []
    # Every candidate routed to the human queue with the policy-disabled reason.
    assert report["human_queue"]
    joined = " ".join(reason for item in report["human_queue"] for reason in item["reasons"])
    assert "disabled" in joined
