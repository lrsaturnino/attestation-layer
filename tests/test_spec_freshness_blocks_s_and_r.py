"""PC-12 — editing a covered module marks its S stale and blocks S ∧ R until revalidated.

The DoD's falsifiable substance: a source edit to a covered module — detected by the Cargo.lock-style
hash invariant (`build_spec_drift_report`) — marks the module's reviewed spec S stale
(`mark_stale_specs`), and the S ∧ R checker then refuses (`unsupported`). The block is attributable to
the SOURCE edit alone: the identical setup over the UNEDITED source checks valid first, and the entry's
`recorded_hash` is None so the spec-file hash is not a competing non-fresh signal — the only non-fresh
signal is the freshness flag `mark_stale_specs` sets. The commit-triggered gate is surfaced report-only
in the continuous run and enforced by the spec-freshness CI step; the committed
`requirements/spec-freshness/` demo config is asserted fresh in the clean tree so green CI means "no
drift", not "gate misconfigured".

The honest RELEASE path — re-validating S against the CHANGED source clears staleness while a blind
hash rebuild does not — is the spec-revalidate flow, proven in test_spec_revalidate_release.py:
these tests prove the block and that it does not lift on a bare re-check.
"""

import hashlib
from pathlib import Path

from nlreq.continuous import build_attestation_run
from nlreq.dsl_v2 import DslV2Parser
from nlreq.impact import ImpactAnalysisArtifact
from nlreq.package import build_package
from nlreq.spec_drift import CodeSpecManifest, build_spec_drift_report, mark_stale_specs
from nlreq.spec_freshness import SpecFreshnessLockfileV2, verify_spec_freshness_validation
from nlreq.system_checker import check_system_consistency_fixture
from nlreq.system_spec import SystemSpecRegistry
from nlreq.translator import lower_ir_v2_to_tla


REQUIREMENT_FIXTURES = Path(__file__).parent / "fixtures" / "requirements"


def _packages_dir_with_one_package(tmp_path: Path) -> Path:
    """A packages dir holding one real, valid requirement package (build_attestation_run requires at
    least one). Mirrors tests/test_continuous.py — the continuous run needs a package index to build."""
    package_root = tmp_path / "requirements"
    build_package(
        controlled_text=(REQUIREMENT_FIXTURES / "authorization_precondition.nlreq").read_text(),
        output_dir=package_root / "REQ-AUTH-001",
        requirement_id="REQ-AUTH-001",
        title="Unauthorized operation is rejected before state changes",
        claim_kind="authorization_precondition",
    )
    return package_root


DSL = (
    "For every redemption:\n"
    "when wallet is authorized\n"
    "and requested_amount <= spendable_balance\n"
    "then finalize_redemption must emit redemption_finalized within 6 hours.\n"
)

SPEC_TLA = (
    "---- MODULE Authorization ----\n"
    "\\* Reviewed system spec S for the covered authorization module.\n"
    "VARIABLE authorized, granted\n\n"
    "AuthorizedOnlyWhenGranted == authorized => granted\n\n"
    "====\n"
)

CLEAN_SOURCE = "def is_authorized(role, action):\n    return action in GRANTS.get(role, set())\n"
EDITED_SOURCE = "def is_authorized(role, action):\n    return True  # over-permissive edit\n"


def _ir():
    return DslV2Parser().parse_ir(DSL, requirement_id="REQ-FRESH-001", title="freshness")


def _impact() -> ImpactAnalysisArtifact:
    return ImpactAnalysisArtifact(
        adapter_id="python-source",
        language="python",
        input_symbols=["is_authorized"],
        affected_modules=["authorization"],
    )


def _setup(tmp_path: Path) -> tuple[CodeSpecManifest, SystemSpecRegistry]:
    """Write the covered source + reviewed spec on disk; return (manifest, registry) over a CLEAN tree.

    `recorded_hash` is None on the registry entry so the spec-file hash is not a freshness signal — the
    only thing that can turn the entry non-fresh is the freshness flag `mark_stale_specs` sets from a
    SOURCE drift, so any block is attributable to the source edit alone.
    """
    src = tmp_path / "authorization.py"
    src.write_text(CLEAN_SOURCE)
    spec_dir = tmp_path / "specs"
    spec_dir.mkdir()
    (spec_dir / "Authorization.tla").write_text(SPEC_TLA)
    source_hash = "sha256:" + hashlib.sha256(src.read_bytes()).hexdigest()
    manifest = CodeSpecManifest.model_validate(
        {
            "schema_version": "0.1",
            "entries": [
                {
                    "module_id": "authorization",
                    "source_paths": ["authorization.py"],
                    "spec_ids": ["spec:authorization"],
                    "recorded_source_hashes": {"authorization.py": source_hash},
                }
            ],
        }
    )
    registry = SystemSpecRegistry.model_validate(
        {
            "schema_version": "0.1",
            "specs": [
                {
                    "spec_id": "spec:authorization",
                    "module_ids": ["authorization"],
                    "formalism": "tla",
                    "path": "specs/Authorization.tla",
                    "version": "1",
                    "review_status": "reviewed",
                    "freshness": "fresh",
                    "recorded_hash": None,
                    "invariants": ["AuthorizedOnlyWhenGranted"],
                }
            ],
        }
    )
    return manifest, registry


def test_fresh_covered_module_lets_s_and_r_run(tmp_path: Path) -> None:
    """Bracket: over the UNEDITED source the identical setup checks valid, so a later block is
    attributable to the source edit alone — not a missing spec file or a lowering artifact."""
    manifest, registry = _setup(tmp_path)

    drift = build_spec_drift_report(manifest, project_root=tmp_path)
    assert drift.result == "passed"
    registry = mark_stale_specs(registry, drift)  # no-op while fresh
    assert registry.specs[0].freshness == "fresh"

    result = check_system_consistency_fixture(
        requirement=_ir(),
        lowered=lower_ir_v2_to_tla(_ir(), legacy_skeleton=True),
        registry=registry,
        impact=_impact(),
        project_root=tmp_path,
    )
    assert result.result.status == "valid"


def test_editing_covered_module_marks_spec_stale_and_blocks_s_and_r(tmp_path: Path) -> None:
    """The DoD composition: edit covered source → drift stale → mark_stale_specs → S ∧ R refuses, and
    the refusal's spec_statuses carry the stale entry with the freshness reason (not just unsupported)."""
    manifest, registry = _setup(tmp_path)

    # Edit the covered module source WITHOUT re-baselining the manifest or re-validating the spec.
    (tmp_path / "authorization.py").write_text(EDITED_SOURCE)

    drift = build_spec_drift_report(manifest, project_root=tmp_path)
    assert drift.result == "blocked"
    assert drift.statuses[0].status == "stale"
    assert drift.statuses[0].changed_paths == ["authorization.py"]

    stale_registry = mark_stale_specs(registry, drift)
    assert stale_registry.specs[0].freshness == "stale"

    result = check_system_consistency_fixture(
        requirement=_ir(),
        lowered=lower_ir_v2_to_tla(_ir(), legacy_skeleton=True),
        registry=stale_registry,
        impact=_impact(),
        project_root=tmp_path,
    )
    assert result.result.status == "unsupported"
    spec_statuses = result.result.details["spec_statuses"]
    assert any(status["status"] == "stale" for status in spec_statuses)
    assert any("freshness" in (status.get("reason") or "") for status in spec_statuses)


def test_stale_spec_stays_blocked_on_bare_recheck(tmp_path: Path) -> None:
    """Without re-validation the block is not transient: re-running the S ∧ R check over the stale
    registry still refuses. (Releasing it requires re-validating S against the changed source — the
    spec-revalidate flow — never a bare re-check or a blind hash rebuild.)"""
    manifest, registry = _setup(tmp_path)
    (tmp_path / "authorization.py").write_text(EDITED_SOURCE)
    stale_registry = mark_stale_specs(
        registry, build_spec_drift_report(manifest, project_root=tmp_path)
    )

    for _ in range(2):
        result = check_system_consistency_fixture(
            requirement=_ir(),
            lowered=lower_ir_v2_to_tla(_ir(), legacy_skeleton=True),
            registry=stale_registry,
            impact=_impact(),
            project_root=tmp_path,
        )
        assert result.result.status == "unsupported"


def test_continuous_run_surfaces_stale_covered_module_report_only(tmp_path: Path) -> None:
    """The continuous run surfaces a drifted covered module as an error-class finding while staying
    report_only — the block lives at the S ∧ R refusal and the CI gate, not in this report."""
    manifest, _registry = _setup(tmp_path)
    (tmp_path / "authorization.py").write_text(EDITED_SOURCE)
    packages_dir = _packages_dir_with_one_package(tmp_path)

    run = build_attestation_run(
        packages_dir,
        code_spec_manifest=manifest,
        code_spec_project_root=tmp_path,
    )

    assert run["result"] == "report_only"
    assert run["summary"]["stale_specs"] == 1
    assert run["spec_freshness"]["result"] == "blocked"
    stale = [finding for finding in run["findings"] if finding["category"] == "stale_spec"]
    assert stale and stale[0]["severity"] == "error"
    assert "authorization" in stale[0]["message"]


def test_continuous_run_without_manifest_has_no_spec_freshness(tmp_path: Path) -> None:
    """The freshness surface is opt-in: a run with no code-spec manifest records no spec_freshness and
    no stale_specs, so existing continuous runs are unchanged."""
    packages_dir = _packages_dir_with_one_package(tmp_path)

    run = build_attestation_run(packages_dir)

    assert run["spec_freshness"] is None
    assert run["summary"]["stale_specs"] == 0


def test_continuous_attestation_cli_surfaces_stale_module(tmp_path: Path) -> None:
    """The continuous-attestation CLI wires --code-spec-manifest through to the freshness surface, so
    the staleness finding is reachable end-to-end (not only programmatically)."""
    from nlreq.cli import main
    from nlreq.jsonutil import read_json

    manifest, _registry = _setup(tmp_path)
    (tmp_path / "authorization.py").write_text(EDITED_SOURCE)
    packages_dir = _packages_dir_with_one_package(tmp_path)
    manifest_path = tmp_path / "code-spec-manifest.json"
    manifest_path.write_text(manifest.model_dump_json())
    out = tmp_path / "run.json"

    main(
        [
            "continuous-attestation",
            str(packages_dir),
            "--code-spec-manifest", str(manifest_path),
            "--code-spec-project-root", str(tmp_path),
            "--out", str(out),
        ]
    )

    report = read_json(out)
    assert report["result"] == "report_only"
    assert report["summary"]["stale_specs"] == 1
    assert report["spec_freshness"]["result"] == "blocked"
    assert any(finding["category"] == "stale_spec" for finding in report["findings"])


COMMITTED_DEMO = Path(__file__).resolve().parents[1] / "requirements" / "spec-freshness"


def test_committed_spec_freshness_demo_verifies_in_clean_tree() -> None:
    """The committed CI demo config (requirements/spec-freshness/) must pass the VALIDATION-AWARE
    gate in a clean tree, so a green spec-freshness CI step means 'no drift AND the recorded
    revalidation evidence verifies' — hash-bound record, real-tool trace provenance, and the
    contract-vs-traces replay re-run here — not 'gate misconfigured'. This also guards the demo
    against silent drift: editing its covered source without running the spec-revalidate release
    flow fails here AND in the CI step."""
    repo_root = COMMITTED_DEMO.parents[1]
    manifest = CodeSpecManifest.model_validate_json((COMMITTED_DEMO / "manifest.json").read_text())
    registry = SystemSpecRegistry.model_validate_json((COMMITTED_DEMO / "registry.json").read_text())
    lockfile = SpecFreshnessLockfileV2.model_validate_json(
        (COMMITTED_DEMO / "lockfile.json").read_text()
    )

    report = verify_spec_freshness_validation(
        manifest=manifest, registry=registry, lockfile=lockfile, project_root=repo_root
    )

    assert report.result == "passed"
    assert all(status.status == "fresh" for status in report.statuses)
    assert all(status.validation_artifacts for status in report.statuses)
