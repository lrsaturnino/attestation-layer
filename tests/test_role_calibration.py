"""Per-role calibration harnesses for the four non-drafting LLM roles (scope §5, ADR 0204 §4).

The translation corpus calibrates ONLY drafting (prose -> controlled -> FormalClaim -> FA/FR).
Each non-drafting role has a different input/output/gold shape, so it needs its own corpus +
harness. These tests prove:

* the harness DISCRIMINATES (non-vacuity): a planted FA is flagged FA, a planted FR is flagged
  FR, a faithful case matches — so the zeros on a faithful corpus are a real signal, not a
  constant-zero instrument;
* the committed discriminator corpora round-trip through ``build_corpora.py`` (no silent drift);
* the committed recorded-discriminator reports are schema-valid and carry the exact expected
  FA/FR (drift guard — a stale ADR/TOML table cannot pass green);
* the ``benchmark-role`` CLI runs the recorded discriminator, stamps a self-describing
  ``calibration`` block on a ``--llm-client`` run, and refuses a bad scheme at exit 2;
* ``benchmark-translation --role <non-drafting>`` still refuses (the translation corpus is
  drafting-only) and now points at ``benchmark-role``.

The live FA/FR measurement is operator-side (``--llm-client live:<model>`` / ``cli:<wrapper>``),
exactly as with drafting; these CI-safe tests use the recorded discriminator + recorded stand-ins.
"""
from __future__ import annotations

import hashlib
import json
import os
import stat
import sys
from pathlib import Path

import pytest

from nlreq.audit_client import AuditVerdict, _AUDIT_PROMPT_VERSION
from nlreq.cli import main
from nlreq.decomposition_client import _DECOMPOSITION_PROMPT_VERSION
from nlreq.llm_client import _EXTRACTION_PROMPT_VERSION, _IMPACT_PROMPT_VERSION
from nlreq.role_calibration import (
    AuditCalibrationCase,
    AuditCalibrationCorpus,
    CalibrationRunError,
    DecompositionCalibrationCase,
    DecompositionCalibrationCorpus,
    ExtractionCalibrationCase,
    ExtractionCalibrationCorpus,
    ImpactCalibrationCase,
    ImpactCalibrationCorpus,
    ModelOutputFailure,
    RoleCalibrationCaseResult,
    RoleCalibrationResults,
    build_role_calibration_report,
    load_role_corpus,
    run_role_calibration,
)

CORPUS_DIR = Path(__file__).resolve().parents[1] / "benchmarks" / "role-calibration"
CALIBRATION_DIR = CORPUS_DIR / "calibration"

_AUTH = (
    "requirement authorization_precondition:\nscope withdrawal\n"
    "when account is not authorized\nthen withdraw must reject before settled\n"
)
_AUTH_INV = _AUTH.replace("when account is not authorized", "when account is authorized")


# ---------------------------------------------------------------------------
# Echo-wrapper + env helpers for the benchmark-role CLI transport tests (iter 4)
# ---------------------------------------------------------------------------
# The ``cli:<wrapper>`` per-call scheme passes NO ``model_env`` (it selects wrapper+tier only),
# so an ``ECHO_MODE`` env var cannot reach the wrapper the way it does in
# ``tests/test_cli_llm_client.py``. These helpers bake the failure MODE into the wrapper script
# as a literal, so each failure mode trips the INTENDED guard on the first case and
# ``CliTransportError`` propagates (iter-4 fix) → ``benchmark-role`` returns exit 2.

_ECHO_MODES = ("ok", "no_sidecar", "bad_route", "tools", "fail")


def _file_sha256(path: Path) -> str:
    """SHA-256 of a wrapper executable's bytes — mirrors ``cli_llm_client._sha256_file`` and the
    operator wrappers' ``_script_sha256`` (raw hexdigest, no prefix)."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _clear_role_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Strip every ``NLREQ_<ROLE>_*`` / ``NLREQ_MODEL_CONFIG`` env var for a clean ladder baseline."""
    for role in ("drafting", "decomposition", "impact", "extraction", "audit"):
        prefix = f"NLREQ_{role.upper()}"
        for suffix in ("CLIENT", "MODEL", "WRAPPER", "TIER", "FIXTURE", "MODEL_ENV", "TIMEOUT_S"):
            monkeypatch.delenv(f"{prefix}_{suffix}", raising=False)
    monkeypatch.delenv("NLREQ_MODEL_CONFIG", raising=False)


def _make_role_echo_wrapper(
    tmp_path: Path,
    *,
    mode: str,
    output_text: str = '["payments","ledger"]',
    provider: str = "echo",
    model: str = "echo-impact-snap",
    wrapper_name: str = "echo-impact",
    name: str = "echo-impact",
) -> Path:
    """An echo wrapper for ``benchmark-role`` transport tests, with the failure MODE baked in.

    Mirrors ``tests/test_cli_llm_client._echo_wrapper_script`` but bakes the mode in as a literal
    (the ``cli:<wrapper>`` scheme passes no ``model_env``, so ``ECHO_MODE`` cannot reach the
    wrapper). The script computes its OWN file hash (matching the operator wrappers'
    ``_script_sha256`` and nlreq's ``_sha256_file``), so the always-on wrapper-hash check passes
    for ``ok`` / ``bad_route`` / ``tools`` and only the INTENDED guard fires. Each failure mode
    fails on the FIRST case, so ``CliTransportError`` propagates (iter-4 fix) and ``benchmark-role``
    returns exit 2 before any report is written.
    """
    if mode not in _ECHO_MODES:
        raise ValueError(f"unknown echo mode {mode!r}")
    script = (
        '#!/usr/bin/env python3\n'
        'import hashlib, json, sys\n'
        'MODE = %r\n'
        'out = sys.argv[2]\n'
        'exit_code = 0\n'
        'with open(out, "w") as f:\n'
        '    f.write(%r)\n'
        'own_hash = hashlib.sha256(open(sys.argv[0], "rb").read()).hexdigest()\n'
        'sidecar_path = out + ".meta.json"\n'
        'sidecar = {"resolved_model": %r, "route": "official", "tools_active": False, '
        '"provider": %r, "wrapper": %r, "wrapper_hash": own_hash, '
        '"cli_version": "echo-1.0", "duration_s": 0.01}\n'
        'if MODE == "no_sidecar":\n'
        '    pass\n'
        'elif MODE == "bad_route":\n'
        '    sidecar["route"] = "openrouter"\n'
        '    json.dump(sidecar, open(sidecar_path, "w"))\n'
        'elif MODE == "tools":\n'
        '    sidecar["tools_active"] = True\n'
        '    json.dump(sidecar, open(sidecar_path, "w"))\n'
        'elif MODE == "fail":\n'
        '    sys.stderr.write("simulated wrapper failure\\n")\n'
        '    exit_code = 1\n'
        'else:\n'
        '    json.dump(sidecar, open(sidecar_path, "w"))\n'
        'sys.exit(exit_code)\n'
    ) % (mode, output_text, model, provider, wrapper_name)
    path = tmp_path / name
    path.write_text(script, encoding="utf-8")
    os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return path


# ---------------------------------------------------------------------------
# Non-vacuity: the harness discriminates (planted FA -> FA, planted FR -> FR, faithful -> match)
# ---------------------------------------------------------------------------


def _decomp_case(case_id: str, fault: str) -> DecompositionCalibrationCase:
    return DecompositionCalibrationCase(
        case_id=case_id, title="t", domain="auth", controlled_text=_AUTH,
        recorded_dsl_text=_AUTH_INV if fault == "false_acceptance" else _AUTH, fault_kind=fault,  # type: ignore[arg-type]
    )


def test_decomposition_discriminator_flags_fa_fr_and_matches() -> None:
    corpus = DecompositionCalibrationCorpus(
        corpus_id="d", version="0.1",
        cases=[_decomp_case("faithful", "faithful"), _decomp_case("fa", "false_acceptance"),
               _decomp_case("fr", "false_refusal")],
    )
    results = run_role_calibration("decomposition", corpus.cases)
    by_id = {r.case_id: r for r in results}
    # Faithful re-expression reproduces the gold FormalClaim signature.
    assert by_id["faithful"].matched and not by_id["faithful"].false_acceptance and not by_id["faithful"].false_refusal
    # An inverted premise lowers to a valid but DIVERGENT claim -> false-acceptance.
    assert by_id["fa"].false_acceptance and not by_id["fa"].false_refusal
    # An IR that does not lower (the harness marks it unsupported) -> false-refusal.
    assert by_id["fr"].false_refusal and not by_id["fr"].false_acceptance


def test_audit_discriminator_flags_fa_fr_and_matches() -> None:
    passed = AuditVerdict(covers_all_clauses=True, invented_premises=[], verdict="passed")
    failed = AuditVerdict(covers_all_clauses=False, invented_premises=["invented"], verdict="failed")
    corpus = AuditCalibrationCorpus(
        corpus_id="a", version="0.1",
        cases=[
            AuditCalibrationCase(case_id="match", title="t", domain="auth", controlled_text=_AUTH,
                                 ir_summary="s", gold_verdict="passed", recorded_verdict=passed, fault_kind="faithful"),
            AuditCalibrationCase(case_id="fa", title="t", domain="auth", controlled_text=_AUTH,
                                 ir_summary="s", gold_verdict="failed", recorded_verdict=passed, fault_kind="false_acceptance"),
            AuditCalibrationCase(case_id="fr", title="t", domain="auth", controlled_text=_AUTH,
                                 ir_summary="s", gold_verdict="passed", recorded_verdict=failed, fault_kind="false_refusal"),
        ],
    )
    by_id = {r.case_id: r for r in run_role_calibration("audit", corpus.cases)}
    assert by_id["match"].matched
    # Auditor passed a faulty decomposition (gold=failed) -> false-acceptance.
    assert by_id["fa"].false_acceptance and not by_id["fa"].false_refusal
    # Auditor failed a correct decomposition (gold=passed) -> false-refusal.
    assert by_id["fr"].false_refusal and not by_id["fr"].false_acceptance


def test_impact_discriminator_supports_partial_overlap_both_fa_and_fr() -> None:
    gold = ["payments", "ledger"]
    corpus = ImpactCalibrationCorpus(
        corpus_id="i", version="0.1",
        cases=[
            ImpactCalibrationCase(case_id="match", title="t", domain="payments", prose="p", symbols=["s"],
                                  candidate_modules=["payments", "ledger", "notify"], gold_affected_modules=gold,
                                  recorded_estimate='["payments","ledger"]', fault_kind="faithful"),
            # Over-claim only (named an extra module) -> FA only.
            ImpactCalibrationCase(case_id="fa", title="t", domain="payments", prose="p", symbols=["s"],
                                  candidate_modules=["payments", "ledger", "notify"], gold_affected_modules=gold,
                                  recorded_estimate='["payments","ledger","notify"]', fault_kind="false_acceptance"),
            # Under-claim only (missed a gold module) -> FR only.
            ImpactCalibrationCase(case_id="fr", title="t", domain="payments", prose="p", symbols=["s"],
                                  candidate_modules=["payments", "ledger", "notify"], gold_affected_modules=gold,
                                  recorded_estimate='["payments"]', fault_kind="false_refusal"),
            # Partial overlap (named an extra AND missed a gold) -> BOTH FA and FR.
            ImpactCalibrationCase(case_id="both", title="t", domain="payments", prose="p", symbols=["s"],
                                  candidate_modules=["payments", "ledger", "notify"], gold_affected_modules=gold,
                                  recorded_estimate='["payments","notify"]', fault_kind="false_acceptance"),
        ],
    )
    by_id = {r.case_id: r for r in run_role_calibration("impact", corpus.cases)}
    assert by_id["match"].matched
    assert by_id["fa"].false_acceptance and not by_id["fa"].false_refusal
    assert by_id["fr"].false_refusal and not by_id["fr"].false_acceptance
    # A set-valued role: a partial-overlap estimate is BOTH an over-claim (FA) and under-claim (FR).
    assert by_id["both"].false_acceptance and by_id["both"].false_refusal


def test_extraction_discriminator_flags_invented_and_missed() -> None:
    gold = [{"name": "S1", "tla": "x >= 0"}]
    corpus = ExtractionCalibrationCorpus(
        corpus_id="e", version="0.1",
        cases=[
            ExtractionCalibrationCase(case_id="match", title="t", domain="payments", module_id="m",
                                      code_presentation="c", language="go", gold_invariants=gold,
                                      recorded_estimate='{"invariants":[{"name":"S1","tla":"x >= 0"}]}', fault_kind="faithful"),
            ExtractionCalibrationCase(case_id="fa", title="t", domain="payments", module_id="m",
                                      code_presentation="c", language="go", gold_invariants=gold,
                                      recorded_estimate='{"invariants":[{"name":"S1","tla":"x >= 0"},{"name":"S2","tla":"y <= 9"}]}',
                                      fault_kind="false_acceptance"),
            ExtractionCalibrationCase(case_id="fr", title="t", domain="payments", module_id="m",
                                      code_presentation="c", language="go", gold_invariants=gold,
                                      recorded_estimate='{"invariants":[]}', fault_kind="false_refusal"),
        ],
    )
    by_id = {r.case_id: r for r in run_role_calibration("extraction", corpus.cases)}
    assert by_id["match"].matched
    assert by_id["fa"].false_acceptance and not by_id["fa"].false_refusal  # invented invariant
    assert by_id["fr"].false_refusal and not by_id["fr"].false_acceptance  # missed invariant


# ---------------------------------------------------------------------------
# Committed corpora round-trip through the generator (no silent drift)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("role", ["decomposition", "audit", "impact", "extraction"])
def test_committed_corpus_round_trips_through_generator(role: str) -> None:
    sys.path.insert(0, str(CORPUS_DIR))
    try:
        import build_corpora  # type: ignore[import-not-found]
    finally:
        sys.path.pop(0)
    expected = json.loads(json.dumps(
        build_corpora.build_all()[role].model_dump(mode="json"), sort_keys=True
    ))
    actual = json.loads((CORPUS_DIR / f"{role}.corpus.json").read_text())
    assert actual == expected, f"{role}.corpus.json is stale; rerun build_corpora.py"


@pytest.mark.parametrize("role", ["decomposition", "audit", "impact", "extraction"])
def test_committed_corpus_has_two_domains_each_with_all_three_fault_kinds(role: str) -> None:
    corpus = load_role_corpus(role, CORPUS_DIR / f"{role}.corpus.json")
    domains = {}
    for case in corpus.cases:
        domains.setdefault(case.domain, set()).add(case.fault_kind)
    # Two distinct domains; each exercises faithful / false_acceptance / false_refusal.
    assert len(domains) >= 2, f"{role}: expected >=2 domains, got {sorted(domains)}"
    for domain, faults in domains.items():
        assert faults == {"faithful", "false_acceptance", "false_refusal"}, (
            f"{role}/{domain}: fault kinds {sorted(faults)}"
        )


# ---------------------------------------------------------------------------
# Committed recorded-discriminator reports: schema-valid + exact FA/FR (drift guard)
# ---------------------------------------------------------------------------

# Each committed report is a recorded-discriminator run over a 12-case corpus (2 domains x
# [2 faithful + 2 FA + 2 FR]): FA=4, FR=4, matched=4, result=failed (the expected non-vacuity
# signal — a constant-zero instrument would pass vacuously). Per-domain: FA=2, FR=2, matched=2.
_COMMITTED_REPORTS = {
    "decomposition": {
        "file": "20260625-decomposition-recorded-discriminator.json",
        "prompt_version": _DECOMPOSITION_PROMPT_VERSION,
    },
    "audit": {
        "file": "20260625-audit-recorded-discriminator.json",
        "prompt_version": _AUDIT_PROMPT_VERSION,
    },
    "impact": {
        "file": "20260625-impact-recorded-discriminator.json",
        "prompt_version": _IMPACT_PROMPT_VERSION,
    },
    "extraction": {
        "file": "20260625-extraction-recorded-discriminator.json",
        "prompt_version": _EXTRACTION_PROMPT_VERSION,
    },
}


@pytest.mark.parametrize("role", ["decomposition", "audit", "impact", "extraction"])
def test_committed_discriminator_report_is_valid_self_describing_evidence(role: str) -> None:
    """The committed recorded-discriminator reports are schema-valid, role-stamped, and carry the
    exact expected FA/FR (drift guard — a stale ADR/TOML table cannot pass green; the JSON is the
    source of truth). A plain recorded ``--run`` has NO ``calibration`` block (byte-stable, like
    the drafting release corpus); the ``role`` field makes the report self-describing by role."""
    from nlreq.role_calibration import RoleCalibrationReport

    spec = _COMMITTED_REPORTS[role]
    report = RoleCalibrationReport.model_validate_json(
        (CALIBRATION_DIR / spec["file"]).read_text()
    )
    assert report.role == role
    assert report.total_cases == 12
    assert report.matched_cases == 4
    assert report.false_acceptance_count == 4
    assert report.false_refusal_count == 4
    assert report.false_acceptance_rate == pytest.approx(4 / 12)
    assert report.false_refusal_rate == pytest.approx(4 / 12)
    assert report.result == "failed"  # the expected non-vacuity signal
    assert report.calibration is None  # plain recorded discriminator: no calibration block
    # Two domains, each FA=2 / FR=2 / matched=2.
    assert len(report.domains) == 2
    for domain in report.domains:
        assert domain.total_cases == 6
        assert domain.false_acceptance_count == 2
        assert domain.false_refusal_count == 2
        assert domain.matched_count == 2
    # Single language for each committed corpus (en for the text roles; go for extraction, which
    # is a source-code role). The per-language slice exists so a future multilingual corpus is
    # structurally representable, exactly as with the drafting report.
    assert len(report.languages) == 1


def test_committed_discriminator_report_set_matches_corpus_roles() -> None:
    """Exactly four committed discriminator reports exist (one per non-drafting role) — a guard
    against a stale report set drifting from the committed evidence."""
    names = sorted(p.name for p in CALIBRATION_DIR.glob("*.json"))
    expected = sorted(spec["file"] for spec in _COMMITTED_REPORTS.values())
    assert names == expected, (
        "role-calibration discriminator report set drifted; update this test + ADR 0204 / nlreq-models.toml"
    )


# ---------------------------------------------------------------------------
# Committed LIVE non-drafting role calibration (iter 4) — acceptance #5 closure
# ---------------------------------------------------------------------------
# iter 4 ran the four non-drafting roles LIVE through the cross-provider CLI transport
# (``benchmark-role --run --llm-client cli:<wrapper>:tiny``) against TWO DISTINCT §6-eligible
# operator wrappers (run-claude → anthropic, run-gpt → openai): 8 self-describing reports, the
# per-role/per-model FA/FR tables acceptance #5 requires. These are single-run snapshots
# (temperature=0, low reasoning effort for run-gpt); live model text is not byte-reproducible,
# so the DURABLE contract is the structural invariant set below (counts + provenance identity),
# NOT the per-case text. Update this map (and ADR 0204 §4.1 / nlreq-models.toml) together ONLY
# when a report is regenerated. The reports live in a SIBLING dir (``live-calibration/``) so the
# recorded-discriminator exact-set guard above stays intact (``calibration/`` is unchanged).

_LIVE_CALIBRATION_DIR = CORPUS_DIR / "live-calibration"
_RUN_GPT_HASH = "0dd5aa277dc9577b43c3fb57c6f710df0f2bbe138f05ca429857f2d4fa553294"
_RUN_CLAUDE_HASH = "5524a2abf5665fa7396432372a473a682fea7570ad2736c7984c7a8425eddaf5"

_LIVE_CALIBRATION_REPORTS = {
    # role / wrapper / provider / resolved_model / total / matched / FA / FR / per-domain (FA,FR) / language / prompt_version
    "20260625-impact-cli-run-gpt-gpt-5.4-mini.json": {
        "role": "impact", "provider": "openai", "wrapper": "run-gpt",
        "resolved_model": "gpt-5.4-mini", "hash": _RUN_GPT_HASH,
        "total": 12, "matched": 2, "fa": 0, "fr": 10,
        "domains": {"payments": (0, 4), "inventory": (0, 6)},
        "language": ("en", (0, 10)), "prompt_version": _IMPACT_PROMPT_VERSION,
    },
    "20260625-impact-cli-run-claude-claude-haiku-4-5.json": {
        "role": "impact", "provider": "anthropic", "wrapper": "run-claude",
        "resolved_model": "claude-haiku-4-5", "hash": _RUN_CLAUDE_HASH,
        "total": 12, "matched": 4, "fa": 1, "fr": 8,
        "domains": {"payments": (1, 2), "inventory": (0, 6)},
        "language": ("en", (1, 8)), "prompt_version": _IMPACT_PROMPT_VERSION,
    },
    "20260625-extraction-cli-run-gpt-gpt-5.4-mini.json": {
        "role": "extraction", "provider": "openai", "wrapper": "run-gpt",
        "resolved_model": "gpt-5.4-mini", "hash": _RUN_GPT_HASH,
        "total": 12, "matched": 0, "fa": 11, "fr": 12,
        "domains": {"payments": (5, 6), "inventory": (6, 6)},
        "language": ("go", (11, 12)), "prompt_version": _EXTRACTION_PROMPT_VERSION,
    },
    "20260625-extraction-cli-run-claude-claude-haiku-4-5.json": {
        "role": "extraction", "provider": "anthropic", "wrapper": "run-claude",
        "resolved_model": "claude-haiku-4-5", "hash": _RUN_CLAUDE_HASH,
        "total": 12, "matched": 0, "fa": 12, "fr": 12,
        "domains": {"payments": (6, 6), "inventory": (6, 6)},
        "language": ("go", (12, 12)), "prompt_version": _EXTRACTION_PROMPT_VERSION,
    },
    "20260625-audit-cli-run-gpt-gpt-5.4-mini.json": {
        "role": "audit", "provider": "openai", "wrapper": "run-gpt",
        "resolved_model": "gpt-5.4-mini", "hash": _RUN_GPT_HASH,
        "total": 12, "matched": 4, "fa": 0, "fr": 8,
        "domains": {"authorization": (0, 4), "procurement": (0, 4)},
        "language": ("en", (0, 8)), "prompt_version": _AUDIT_PROMPT_VERSION,
    },
    "20260625-audit-cli-run-claude-claude-haiku-4-5.json": {
        "role": "audit", "provider": "anthropic", "wrapper": "run-claude",
        "resolved_model": "claude-haiku-4-5", "hash": _RUN_CLAUDE_HASH,
        "total": 12, "matched": 4, "fa": 0, "fr": 8,
        "domains": {"authorization": (0, 4), "procurement": (0, 4)},
        "language": ("en", (0, 8)), "prompt_version": _AUDIT_PROMPT_VERSION,
    },
    "20260625-decomposition-cli-run-gpt-gpt-5.4-mini.json": {
        "role": "decomposition", "provider": "openai", "wrapper": "run-gpt",
        "resolved_model": "gpt-5.4-mini", "hash": _RUN_GPT_HASH,
        "total": 12, "matched": 10, "fa": 0, "fr": 2,
        "domains": {"authorization": (0, 1), "procurement": (0, 1)},
        "language": ("en", (0, 2)), "prompt_version": _DECOMPOSITION_PROMPT_VERSION,
    },
    "20260625-decomposition-cli-run-claude-claude-haiku-4-5.json": {
        "role": "decomposition", "provider": "anthropic", "wrapper": "run-claude",
        "resolved_model": "claude-haiku-4-5", "hash": _RUN_CLAUDE_HASH,
        "total": 12, "matched": 11, "fa": 0, "fr": 1,
        "domains": {"authorization": (0, 1), "procurement": (0, 0)},
        "language": ("en", (0, 1)), "prompt_version": _DECOMPOSITION_PROMPT_VERSION,
    },
}


@pytest.mark.parametrize("name", sorted(_LIVE_CALIBRATION_REPORTS))
def test_committed_live_role_calibration_report_is_valid_self_describing_evidence(name: str) -> None:
    """iter-4 acceptance #5 closure: the 8 committed LIVE non-drafting calibration reports
    (4 roles x 2 providers) are schema-valid, self-describing, and carry the exact committed
    FA/FR counts + CLI-transport provenance (ADR 0204 §4.1 / §5).

    Each report round-trips through ``RoleCalibrationReport`` and its ``calibration`` block
    records client_kind='cli' + the sidecar's provider / resolved_model / wrapper / route /
    wrapper_hash / cli_version / prompt_version / transport_source — so the per-role/per-model
    FA/FR tables stand alone without external filenames. The exact total/matched/FA/FR +
    per-domain + per-language counts are regression-asserted against the committed JSON (the
    source of truth); a stale ADR 0204 / nlreq-models.toml prose table cannot pass green. The
    wrapper_hash is exact-asserted (it binds the snapshot to the specific wrapper version that
    produced it; the hashes match the drafting CLI reports + the committed ensemble artifact).
    Live model text is not byte-reproducible, so the counts + provenance identity are the durable
    contract — update this map (and ADR 0204 §4.1 / nlreq-models.toml) ONLY on regeneration.
    """
    from nlreq.role_calibration import RoleCalibrationReport

    spec = _LIVE_CALIBRATION_REPORTS[name]
    report = RoleCalibrationReport.model_validate_json(
        (_LIVE_CALIBRATION_DIR / name).read_text()
    )
    cal = report.calibration
    assert cal is not None, f"{name} has no calibration block"
    assert cal.role == spec["role"], f"{name}: role={cal.role!r}"
    assert cal.client_kind == "cli", f"{name}: client_kind={cal.client_kind!r}"
    assert cal.provider == spec["provider"], f"{name}: provider={cal.provider!r}"
    assert cal.wrapper == spec["wrapper"], f"{name}: wrapper={cal.wrapper!r}"
    assert cal.resolved_model == spec["resolved_model"], f"{name}: resolved_model={cal.resolved_model!r}"
    assert cal.resolved_model in name, f"{name}: resolved_model not reflected in filename"
    assert cal.route == "official", f"{name}: route={cal.route!r} (silent fallback hazard)"
    assert cal.wrapper_hash == spec["hash"], f"{name}: wrapper_hash={cal.wrapper_hash!r}"
    assert cal.cli_version, f"{name}: missing cli_version"
    assert cal.prompt_version == spec["prompt_version"], f"{name}: prompt_version={cal.prompt_version!r}"
    assert cal.transport_source == "override", f"{name}: transport_source={cal.transport_source!r}"
    # Exact total/matched/FA/FR — the committed JSON is the source of truth.
    assert report.total_cases == spec["total"], f"{name}: total={report.total_cases}"
    assert report.matched_cases == spec["matched"], f"{name}: matched={report.matched_cases}"
    assert report.false_acceptance_count == spec["fa"], f"{name}: FA={report.false_acceptance_count}"
    assert report.false_refusal_count == spec["fr"], f"{name}: FR={report.false_refusal_count}"
    assert report.result == "failed", f"{name}: expected 'failed' (non-viable live role model)"
    # Exact per-domain + per-language FA/FR (regression-guard the committed subgroup totals).
    for dm in report.domains:
        assert dm.label in spec["domains"], f"{name}: unexpected domain {dm.label!r}"
        exp_fa, exp_fr = spec["domains"][dm.label]
        assert dm.false_acceptance_count == exp_fa, f"{name}/{dm.label}: FA={dm.false_acceptance_count}"
        assert dm.false_refusal_count == exp_fr, f"{name}/{dm.label}: FR={dm.false_refusal_count}"
    assert len(report.domains) == 2, f"{name}: expected 2 domains"
    lang_label, (lang_fa, lang_fr) = spec["language"]
    assert len(report.languages) == 1, f"{name}: expected 1 language"
    lm = report.languages[0]
    assert lm.label == lang_label, f"{name}: language={lm.label!r}"
    assert lm.false_acceptance_count == lang_fa, f"{name}/{lang_label}: FA={lm.false_acceptance_count}"
    assert lm.false_refusal_count == lang_fr, f"{name}/{lang_label}: FR={lm.false_refusal_count}"


def test_committed_live_role_calibration_set_matches_expected() -> None:
    """Exactly eight committed live non-drafting calibration reports exist (4 roles x 2 providers)
    — a guard against a stale live-evidence set drifting from the committed reports."""
    names = sorted(p.name for p in _LIVE_CALIBRATION_DIR.glob("*.json"))
    assert names == sorted(_LIVE_CALIBRATION_REPORTS), (
        "role-calibration LIVE report set drifted; update this test + ADR 0204 §4.1 / nlreq-models.toml"
    )


def test_committed_live_role_calibration_records_two_distinct_providers_per_role() -> None:
    """Acceptance #5 (cross-provider dimension, non-drafting): for each non-drafting role the two
    committed live reports record TWO DISTINCT providers (anthropic via run-claude + openai via
    run-gpt), two distinct resolved model ids, and two distinct wrapper hashes — the cross-provider
    diversity the scope's policy wants, now calibrated live for every non-drafting role (ADR 0204
    §1/§4.1)."""
    from nlreq.role_calibration import RoleCalibrationReport

    by_role: dict[str, list] = {}
    for name in _LIVE_CALIBRATION_REPORTS:
        report = RoleCalibrationReport.model_validate_json(
            (_LIVE_CALIBRATION_DIR / name).read_text()
        )
        by_role.setdefault(report.role, []).append(report)
    assert sorted(by_role) == ["audit", "decomposition", "extraction", "impact"]
    for role, reports in by_role.items():
        assert len(reports) == 2, f"{role}: expected 2 live reports, got {len(reports)}"
        providers = {r.calibration.provider for r in reports}
        models = {r.calibration.resolved_model for r in reports}
        hashes = {r.calibration.wrapper_hash for r in reports}
        wrappers = {r.calibration.wrapper for r in reports}
        assert providers == {"anthropic", "openai"}, f"{role}: providers={providers}"
        assert len(models) == 2, f"{role}: expected 2 distinct models, got {models}"
        assert len(hashes) == 2, f"{role}: expected 2 distinct wrapper hashes, got {hashes}"
        assert wrappers == {"run-claude", "run-gpt"}, f"{role}: wrappers={wrappers}"


# ---------------------------------------------------------------------------
# CLI: benchmark-role
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("role", ["decomposition", "audit", "impact", "extraction"])
def test_cli_benchmark_role_recorded_discriminator_run(role: str, tmp_path: Path) -> None:
    """``benchmark-role --run`` (no --llm-client) replays each case's recorded output and emits the
    self-describing FA/FR report with the expected discriminator counts."""
    out = tmp_path / "report.json"
    exit_code = main([
        "benchmark-role", "--role", role,
        "--corpus", str(CORPUS_DIR / f"{role}.corpus.json"),
        "--run", "--out", str(out),
    ])
    assert exit_code == 1  # failed = non-zero FA/FR (the expected discriminator signal)
    report = json.loads(out.read_text())
    assert report["role"] == role
    assert report["false_acceptance_count"] == 4
    assert report["false_refusal_count"] == 4
    assert report["matched_cases"] == 4
    assert report.get("calibration") is None  # plain recorded run: calibration block omitted (exclude_none)


def test_cli_benchmark_role_llm_client_recorded_stamps_calibration(tmp_path: Path) -> None:
    """``--llm-client recorded:<fixture>`` routes through the per-role factory and stamps a
    self-describing ``calibration`` block (role / client_kind / prompt_version / transport_source),
    so the FA/FR tables stand alone without external filenames or prose."""
    fixture = tmp_path / "fixture.txt"
    fixture.write_text('["payments","ledger"]')
    out = tmp_path / "report.json"
    exit_code = main([
        "benchmark-role", "--role", "impact",
        "--corpus", str(CORPUS_DIR / "impact.corpus.json"),
        "--run", "--llm-client", f"recorded:{fixture}", "--out", str(out),
    ])
    assert exit_code in (0, 1)  # FA/FR may be nonzero; provenance stamping is what is tested
    report = json.loads(out.read_text())
    cal = report["calibration"]
    assert cal is not None
    assert cal["role"] == "impact"
    assert cal["client_kind"] == "recorded"
    assert cal["prompt_version"] == _IMPACT_PROMPT_VERSION
    assert cal["transport_source"] == "override"


def test_cli_benchmark_role_bad_scheme_exits_2(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """A bad ``--llm-client`` scheme refuses at exit 2 (``nlreq:``) before any case runs."""
    exit_code = main([
        "benchmark-role", "--role", "impact",
        "--corpus", str(CORPUS_DIR / "impact.corpus.json"),
        "--run", "--llm-client", "bogus-scheme-xyz",
    ])
    assert exit_code == 2
    assert "unknown client spec" in capsys.readouterr().err


def test_cli_benchmark_role_bad_model_config_exits_2(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """A malformed ``--model-config`` refuses at exit 2 (``nlreq:``), consistent with the other
    model-config paths — never the generic top-level error path."""
    bad = tmp_path / "bad.toml"
    bad.write_text("not = valid = toml =")
    exit_code = main([
        "benchmark-role", "--role", "impact",
        "--corpus", str(CORPUS_DIR / "impact.corpus.json"),
        "--run", "--llm-client", "live:claude-haiku-4-5-20251001",
        "--model-config", str(bad),
    ])
    assert exit_code == 2
    err = capsys.readouterr().err
    assert "nlreq:" in err
    assert "error:" not in err
    assert "Traceback" not in err


def test_cli_benchmark_role_requires_run_or_results(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main([
        "benchmark-role", "--role", "audit",
        "--corpus", str(CORPUS_DIR / "audit.corpus.json"),
    ])
    assert exit_code == 2
    assert "requires --results or --run" in capsys.readouterr().err


def test_cli_benchmark_role_results_round_trips(tmp_path: Path) -> None:
    """``--results`` reads pre-computed case results and builds the same report as ``--run``
    (a calibration can be computed once and reported separately, mirroring ``benchmark-translation``).
    The two reports are byte-identical in their FA/FR/matched totals."""
    run_out = tmp_path / "run-report.json"
    main([
        "benchmark-role", "--role", "audit",
        "--corpus", str(CORPUS_DIR / "audit.corpus.json"),
        "--run", "--out", str(run_out),
    ])
    run_report = json.loads(run_out.read_text())
    # Serialize the run's observations as a RoleCalibrationResults file, then report from it.
    results_payload = RoleCalibrationResults(
        role="audit",
        results=[RoleCalibrationCaseResult.model_validate(obs) for obs in run_report["observations"]],
    )
    results_path = tmp_path / "results.json"
    results_path.write_text(results_payload.model_dump_json())
    res_out = tmp_path / "res-report.json"
    exit_code = main([
        "benchmark-role", "--role", "audit",
        "--corpus", str(CORPUS_DIR / "audit.corpus.json"),
        "--results", str(results_path), "--out", str(res_out),
    ])
    assert exit_code == 1  # same failed (non-zero FA/FR) signal as the --run report
    res_report = json.loads(res_out.read_text())
    assert res_report["false_acceptance_count"] == run_report["false_acceptance_count"]
    assert res_report["false_refusal_count"] == run_report["false_refusal_count"]
    assert res_report["matched_cases"] == run_report["matched_cases"]


# ---------------------------------------------------------------------------
# iter-4: CLI transport failure modes refuse at exit 2 (BLOCKING fix #1/#2)
# ---------------------------------------------------------------------------
# A CLI transport that violates the pure-completion contract (missing sidecar / route mismatch /
# tools active / non-zero exit) must make ``benchmark-role`` return exit 2 with ``nlreq:`` stderr
# and NO accepted calibration report — never a silent false-refusal buried in the report. Before
# the iter-4 fix, ``_run_case`` captured every ``Exception`` (including ``CliTransportError``)
# as a scored outcome, so the scorer recorded a false-refusal and the CLI's ``except
# CliTransportError`` was unreachable. Now ``CliTransportError`` propagates out of
# ``run_role_calibration``, the CLI converts it to exit 2, and no report is written.


@pytest.mark.parametrize(
    "mode, needle",
    [
        ("no_sidecar", "no meta sidecar"),
        ("bad_route", "route mismatch"),
        ("tools", "tools active"),
        ("fail", "exited 1"),
    ],
)
def test_cli_benchmark_role_cli_transport_failure_exits_2_without_report(
    mode: str,
    needle: str,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_role_env(monkeypatch)
    wrapper = _make_role_echo_wrapper(tmp_path, mode=mode)
    out = tmp_path / "report.json"
    exit_code = main([
        "benchmark-role", "--role", "impact",
        "--corpus", str(CORPUS_DIR / "impact.corpus.json"),
        "--run", "--llm-client", f"cli:{wrapper}",
        "--out", str(out),
    ])
    assert exit_code == 2, f"mode={mode}: expected exit 2 (structured refusal), got {exit_code}"
    err = capsys.readouterr().err
    assert "nlreq:" in err, f"mode={mode}: expected `nlreq:` stderr, got: {err!r}"
    assert needle in err, f"mode={mode}: expected {needle!r} in stderr, got: {err!r}"
    assert "Traceback" not in err
    # No accepted calibration report is written on a transport refusal: the CLI returns 2 before
    # build_role_calibration_report / write_json ever run.
    assert not out.exists(), f"mode={mode}: a transport refusal must not write a report"


def test_cli_benchmark_role_cli_ok_run_stamps_calibration_and_completes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The ``benchmark-role --llm-client cli:<wrapper>`` SUCCESS path completes (exit 0/1, not 2)
    and stamps a self-describing ``calibration`` block with the sidecar's provider / resolved
    model / wrapper / wrapper_hash / prompt_version / transport_source.

    This is the end-to-end live-cli path the failure-mode tests bracket: it verifies the path
    works before any real wrapper is invoked, and that the iter-4 ``CliTransportError``-
    propagation fix did not break the success path (a successful call never raises it). Provenance
    records the sidecar-resolved model id, NEVER the tier (scope §4)."""
    _clear_role_env(monkeypatch)
    wrapper = _make_role_echo_wrapper(
        tmp_path, mode="ok", output_text='["payments","ledger"]',
        provider="echo", model="echo-impact-snap", wrapper_name="echo-impact",
    )
    out = tmp_path / "report.json"
    exit_code = main([
        "benchmark-role", "--role", "impact",
        "--corpus", str(CORPUS_DIR / "impact.corpus.json"),
        "--run", "--llm-client", f"cli:{wrapper}",
        "--out", str(out),
    ])
    assert exit_code in (0, 1), f"expected 0/1 (completed run), got {exit_code}"
    report = json.loads(out.read_text())
    cal = report["calibration"]
    assert cal is not None
    assert cal["role"] == "impact"
    assert cal["client_kind"] == "cli"
    assert cal["provider"] == "echo"
    assert cal["resolved_model"] == "echo-impact-snap"  # sidecar id, not a tier
    assert cal["wrapper"] == "echo-impact"
    assert cal["wrapper_hash"] == _file_sha256(wrapper)
    assert cal["prompt_version"] == _IMPACT_PROMPT_VERSION
    assert cal["transport_source"] == "override"
    assert "tier" not in cal  # never the tier


# ---------------------------------------------------------------------------
# iter-4: --results validation refuses mismatched results (MEDIUM fix #5)
# ---------------------------------------------------------------------------
# A truncated / duplicated / extra-case results file is a structured refusal (exit 2, ``nlreq:``),
# never zeroed FA/FR rates from a partial file. Missing cases must be explicit observations or a
# refusal, not silent zeros.


def _audit_run_observations(tmp_path: Path) -> list[dict]:
    """Run the recorded audit discriminator and return its observations (a complete, valid set)."""
    run_out = tmp_path / "run.json"
    main([
        "benchmark-role", "--role", "audit",
        "--corpus", str(CORPUS_DIR / "audit.corpus.json"),
        "--run", "--out", str(run_out),
    ])
    return json.loads(run_out.read_text())["observations"]


def test_cli_benchmark_role_truncated_results_exits_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A truncated ``--results`` file (missing cases) refuses at exit 2, never zeroed rates."""
    obs = _audit_run_observations(tmp_path)
    truncated = RoleCalibrationResults(
        role="audit",
        results=[RoleCalibrationCaseResult.model_validate(o) for o in obs[:3]],  # 3 of 12
    )
    res_path = tmp_path / "truncated.json"
    res_path.write_text(truncated.model_dump_json())
    out = tmp_path / "report.json"
    exit_code = main([
        "benchmark-role", "--role", "audit",
        "--corpus", str(CORPUS_DIR / "audit.corpus.json"),
        "--results", str(res_path), "--out", str(out),
    ])
    assert exit_code == 2
    err = capsys.readouterr().err
    assert "nlreq:" in err
    assert "missing case ids" in err
    assert not out.exists()


def test_cli_benchmark_role_duplicate_results_exits_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A ``--results`` file with a duplicate case id refuses at exit 2."""
    obs = _audit_run_observations(tmp_path)
    results_list = [RoleCalibrationCaseResult.model_validate(o) for o in obs]
    results_list.append(results_list[0])  # duplicate the first case's result (13 total)
    duplicated = RoleCalibrationResults(role="audit", results=results_list)
    res_path = tmp_path / "duplicated.json"
    res_path.write_text(duplicated.model_dump_json())
    out = tmp_path / "report.json"
    exit_code = main([
        "benchmark-role", "--role", "audit",
        "--corpus", str(CORPUS_DIR / "audit.corpus.json"),
        "--results", str(res_path), "--out", str(out),
    ])
    assert exit_code == 2
    err = capsys.readouterr().err
    assert "nlreq:" in err
    assert "duplicate case ids" in err
    assert not out.exists()


def test_cli_benchmark_role_extra_results_exits_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A ``--results`` file with a case id not in the corpus refuses at exit 2."""
    obs = _audit_run_observations(tmp_path)
    results_list = [RoleCalibrationCaseResult.model_validate(o) for o in obs]
    results_list.append(
        RoleCalibrationCaseResult(case_id="nonexistent-case", fault_kind="faithful", matched=True)
    )
    with_extra = RoleCalibrationResults(role="audit", results=results_list)
    res_path = tmp_path / "extra.json"
    res_path.write_text(with_extra.model_dump_json())
    out = tmp_path / "report.json"
    exit_code = main([
        "benchmark-role", "--role", "audit",
        "--corpus", str(CORPUS_DIR / "audit.corpus.json"),
        "--results", str(res_path), "--out", str(out),
    ])
    assert exit_code == 2
    err = capsys.readouterr().err
    assert "nlreq:" in err
    assert "extra case ids" in err
    assert not out.exists()


def test_cli_benchmark_role_malformed_results_file_exits_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A non-JSON / schema-invalid ``--results`` file refuses at exit 2 (``nlreq:``), not the
    generic top-level traceback path."""
    bad = tmp_path / "bad.json"
    bad.write_text("not json at all")
    out = tmp_path / "report.json"
    exit_code = main([
        "benchmark-role", "--role", "audit",
        "--corpus", str(CORPUS_DIR / "audit.corpus.json"),
        "--results", str(bad), "--out", str(out),
    ])
    assert exit_code == 2
    err = capsys.readouterr().err
    assert "nlreq:" in err
    assert "results file is invalid" in err
    assert "Traceback" not in err
    assert not out.exists()


# ---------------------------------------------------------------------------
# iter-7: non-CLI infrastructure failures surface as CalibrationRunError (BLOCKING fix)
# ---------------------------------------------------------------------------
# Before iter-7, ``_run_case`` caught EVERY ``Exception`` (after CliTransportError) and returned
# it as the scored outcome, so a non-CLI infrastructure failure (missing API key / SDK, an
# auth/network/rate-limit SDK error, OSError, ImportError) reached the scorers, which called
# ``outcome.requirement`` / ``outcome.verdict`` / ``parse_impact_estimate(outcome).strip()`` on
# the bare exception and crashed (AttributeError) instead of surfacing a structured refusal.
# Now ``_run_case`` returns ONLY explicit ``ModelOutputFailure`` (scoreable false-refusal) and
# wraps an unparseable decomposition (``DslV3ParseError``) into one; every other failure raises
# ``CalibrationRunError``, which ``benchmark-role`` converts to exit 2 with NO report.


class _RaisingClient:
    """A role-client double whose every method raises a configured exception.

    Simulates a live client infrastructure failure (missing SDK, auth/network/rate-limit SDK
    error, OS error) OR an explicit model-output failure, so the iter-7 ``_run_case`` taxonomy
    can be exercised without a real provider. Method signatures match the four role dispatches
    in ``_run_case``.
    """

    def __init__(self, exc: BaseException) -> None:
        self._exc = exc

    def decompose_controlled_to_ir(self, controlled_text, *, requirement_id, title):
        raise self._exc

    def audit_decomposition(self, *, controlled_text, ir_summary):
        raise self._exc

    def estimate_impacted_modules(self, *, prose, symbols, candidate_modules):
        raise self._exc

    def extract_spec_invariants(self, *, module_id, code_presentation, language="en"):
        raise self._exc


@pytest.mark.parametrize(
    "exc",
    [
        OSError("simulated network/IO failure"),
        ImportError("simulated missing provider SDK"),
        ConnectionError("simulated auth/network SDK error"),
        RuntimeError("simulated rate-limit SDK error"),
    ],
    ids=["oserror", "importerror", "connectionerror", "runtimeerror"],
)
def test_run_role_calibration_raises_calibration_run_error_for_infrastructure_failure(
    exc: BaseException,
) -> None:
    """A non-CLI live-client infrastructure failure (OSError / ImportError / SDK auth|network|
    rate-limit) never reaches a scoreable model output: ``_run_case`` raises
    ``CalibrationRunError`` so ``benchmark-role`` refuses at exit 2 with no report — never a
    silent false-refusal in the evidence and never a scorer crash (the pre-iter-7 ``return exc``
    path fed the bare exception to parsers calling ``.strip()`` / ``.requirement``)."""
    corpus = load_role_corpus("impact", CORPUS_DIR / "impact.corpus.json")
    client = _RaisingClient(exc)
    with pytest.raises(CalibrationRunError):
        run_role_calibration("impact", corpus.cases, client=client)


def test_run_role_calibration_scores_explicit_model_output_failure_as_false_refusal() -> None:
    """An explicit ``ModelOutputFailure`` (a live client that contacted the model but produced
    unusable output) IS scoreable: the model answered, so it is a conservative false-refusal,
    not an infrastructure refusal. The scorer records FR for every case rather than raising."""
    corpus = load_role_corpus("impact", CORPUS_DIR / "impact.corpus.json")
    client = _RaisingClient(ModelOutputFailure("simulated unusable model output"))
    results = run_role_calibration("impact", corpus.cases, client=client)
    assert len(results) == len(corpus.cases)
    assert all(r.false_refusal for r in results)
    assert all(not r.false_acceptance for r in results)
    assert all(not r.matched for r in results)


def test_run_role_calibration_scores_unparseable_decomposition_as_false_refusal() -> None:
    """A live decomposer that emits unparseable DSL v3 (``DslV3ParseError``) DID answer — the
    output was just unusable — so ``_run_case`` wraps it into a ``ModelOutputFailure`` and the
    scorer records a conservative false-refusal, rather than raising ``CalibrationRunError``
    (which would treat a model-output failure as an infrastructure refusal)."""
    from nlreq.dsl_v3 import DslV3ParseError

    corpus = load_role_corpus("decomposition", CORPUS_DIR / "decomposition.corpus.json")
    client = _RaisingClient(DslV3ParseError("simulated unparseable re-expression"))
    results = run_role_calibration("decomposition", corpus.cases, client=client)
    assert len(results) == len(corpus.cases)
    assert all(r.false_refusal for r in results)
    assert all(not r.matched for r in results)


def test_cli_benchmark_role_infrastructure_failure_exits_2_without_report(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """End-to-end: a live ``--llm-client`` client that raises a non-CLI infrastructure failure
    (here OSError, simulating a missing provider SDK / network failure) on a case surfaces as
    ``CalibrationRunError`` from the REAL ``run_role_calibration`` → ``benchmark-role`` returns
    exit 2 with ``nlreq:`` stderr and NO report — never a silent false-refusal and never a
    scorer crash. The client is injected by stubbing ``_resolve_client_scheme`` so the real
    ``_run_case`` taxonomy runs deterministically without provider auth."""
    import types as _types

    import nlreq.cli as _cli

    _clear_role_env(monkeypatch)
    failing = _RaisingClient(OSError("simulated missing provider SDK / network failure"))
    monkeypatch.setattr(
        _cli,
        "_resolve_client_scheme",
        lambda spec, role, model_config: _types.SimpleNamespace(client=failing),
    )
    out = tmp_path / "report.json"
    exit_code = main([
        "benchmark-role", "--role", "impact",
        "--corpus", str(CORPUS_DIR / "impact.corpus.json"),
        "--run", "--llm-client", "live:claude-haiku-4-5-20251001",  # scheme is stubbed
        "--out", str(out),
    ])
    assert exit_code == 2
    err = capsys.readouterr().err
    assert "nlreq:" in err
    assert "calibration run error" in err
    assert "Traceback" not in err
    assert not out.exists(), "an infrastructure refusal must not write a report"


def test_cli_benchmark_role_results_role_mismatch_exits_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A ``--results`` file whose top-level ``role`` disagrees with ``--role`` is a structured
    refusal (exit 2, ``nlreq:``): the results file's role is part of its self-description, so a
    payload stamped for one role must not be reported under another (false provenance — case ids
    may coincide but the scorer/semantics differ). Previously ``--results`` discarded the parsed
    role and reported whatever ``--role`` was given."""
    obs = _audit_run_observations(tmp_path)
    # A valid audit results set, but STAMPED role="impact" — mismatched against --role audit.
    mismatched = RoleCalibrationResults(
        role="impact",
        results=[RoleCalibrationCaseResult.model_validate(o) for o in obs],
    )
    res_path = tmp_path / "mismatched.json"
    res_path.write_text(mismatched.model_dump_json())
    out = tmp_path / "report.json"
    exit_code = main([
        "benchmark-role", "--role", "audit",
        "--corpus", str(CORPUS_DIR / "audit.corpus.json"),
        "--results", str(res_path), "--out", str(out),
    ])
    assert exit_code == 2
    err = capsys.readouterr().err
    assert "nlreq:" in err
    assert "does not match" in err
    assert "impact" in err
    assert "audit" in err
    assert not out.exists()


# ---------------------------------------------------------------------------
# benchmark-translation --role <non-drafting> still refuses, now pointing at benchmark-role
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("role", ["impact", "extraction", "decomposition", "audit"])
def test_benchmark_translation_non_drafting_role_refusal_points_to_benchmark_role(
    role: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The translation corpus calibrates ONLY drafting; a non-drafting ``--role`` is refused (exit 2)
    and the message points at ``benchmark-role`` (the role-specific harness), so the non-drafting
    dimension is no longer 'future scope / refused everywhere'."""
    corpus_path = tmp_path / "corpus.json"
    corpus_path.write_text(_tiny_translation_corpus().model_dump_json())
    fixture = tmp_path / "fixture.txt"
    fixture.write_text(_AUTH)
    exit_code = main([
        "benchmark-translation", "--corpus", str(corpus_path), "--run",
        "--llm-client", f"recorded:{fixture}", "--role", role,
    ])
    assert exit_code == 2
    err = capsys.readouterr().err
    assert "not calibratable" in err
    assert "benchmark-role" in err


def _tiny_translation_corpus():
    from nlreq.translation_benchmark import (
        RequirementTranslationCase, RequirementTranslationCorpus, RequirementTranslationExpected,
    )
    return RequirementTranslationCorpus(
        corpus_id="tiny", version="0.1",
        cases=[RequirementTranslationCase(
            case_id="c1", title="t", input_text="Reject an unauthorized withdrawal.",
            input_kind="messy_prose", domain="d", language="en",
            gold_controlled_text=_AUTH, recorded_controlled_text=_AUTH,
            expected=RequirementTranslationExpected(outcome="accepted"),  # type: ignore[arg-type]
        )],
    )
