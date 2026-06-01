import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from nlreq.cli import main
from nlreq.impact import ImpactAnalysisArtifact
from nlreq.system_spec import (
    SystemSpecRegistry,
    build_system_spec_registry_report,
    specs_for_impact,
)


def test_system_spec_registry_reports_fresh_reviewed_specs(tmp_path: Path) -> None:
    registry = _registry(tmp_path)

    report = build_system_spec_registry_report(registry, project_root=tmp_path)

    assert report.result == "valid"
    assert report.statuses[0].status == "fresh"
    assert report.statuses[0].current_hash is not None


def test_system_spec_registry_reports_stale_hash(tmp_path: Path) -> None:
    registry = _registry(tmp_path, recorded_hash="sha256:stale")

    report = build_system_spec_registry_report(registry, project_root=tmp_path)

    assert report.result == "needs_review"
    assert report.statuses[0].status == "stale"
    assert report.statuses[0].reason == "recorded hash does not match current spec"


def test_system_spec_registry_reports_missing_and_unreviewed_specs(tmp_path: Path) -> None:
    registry = SystemSpecRegistry.model_validate(
        {
            "schema_version": "0.1",
            "specs": [
                {
                    "spec_id": "spec:missing",
                    "module_ids": ["missing"],
                    "formalism": "tla",
                    "path": "specs/Missing.tla",
                    "version": "1",
                    "review_status": "reviewed",
                    "freshness": "fresh",
                },
                {
                    "spec_id": "spec:draft",
                    "module_ids": ["draft"],
                    "formalism": "tla",
                    "path": "specs/Draft.tla",
                    "version": "1",
                    "review_status": "draft",
                    "freshness": "fresh",
                },
            ],
        }
    )
    (tmp_path / "specs").mkdir()
    (tmp_path / "specs" / "Draft.tla").write_text("---- MODULE Draft ----\n====\n")

    report = build_system_spec_registry_report(registry, project_root=tmp_path)

    assert [status.status for status in report.statuses] == ["missing", "unreviewed"]


def test_system_spec_registry_rejects_escaping_paths() -> None:
    with pytest.raises(ValidationError):
        SystemSpecRegistry.model_validate(
            {
                "schema_version": "0.1",
                "specs": [
                    {
                        "spec_id": "spec:bad",
                        "module_ids": ["bad"],
                        "formalism": "tla",
                        "path": "../Bad.tla",
                        "version": "1",
                        "review_status": "reviewed",
                    }
                ],
            }
        )


def test_specs_for_impact_returns_relevant_system_specs(tmp_path: Path) -> None:
    registry = _registry(tmp_path)
    impact = ImpactAnalysisArtifact(
        adapter_id="python-source",
        language="python",
        input_symbols=["operation"],
        affected_modules=["auth"],
    )

    specs = specs_for_impact(registry, impact)

    assert [spec.spec_id for spec in specs] == ["spec:auth"]


def test_system_spec_registry_cli(tmp_path: Path, capsys) -> None:
    registry = _registry(tmp_path)
    path = tmp_path / "system-spec-registry.json"
    out = tmp_path / "system-spec-report.json"
    path.write_text(json.dumps(registry.model_dump(mode="json"), indent=2))

    exit_code = main(
        [
            "system-spec-registry",
            str(path),
            "--project-root",
            str(tmp_path),
            "--module-id",
            "auth",
            "--out",
            str(out),
        ]
    )

    output = capsys.readouterr().out

    assert exit_code == 0
    assert "System spec registry report:" in output
    assert json.loads(out.read_text())["result"] == "valid"


def _registry(tmp_path: Path, *, recorded_hash: str | None = None) -> SystemSpecRegistry:
    specs = tmp_path / "specs"
    specs.mkdir(exist_ok=True)
    (specs / "Auth.tla").write_text("---- MODULE Auth ----\nAuthInvariant == TRUE\n====\n")
    return SystemSpecRegistry.model_validate(
        {
            "schema_version": "0.1",
            "specs": [
                {
                    "spec_id": "spec:auth",
                    "module_ids": ["auth"],
                    "formalism": "tla",
                    "path": "specs/Auth.tla",
                    "version": "1",
                    "review_status": "reviewed",
                    "freshness": "fresh",
                    "recorded_hash": recorded_hash,
                }
            ],
        }
    )
