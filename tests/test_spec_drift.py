import hashlib
from pathlib import Path

from nlreq.cli import main
from nlreq.jsonutil import read_json
from nlreq.spec_drift import (
    CodeSpecManifest,
    build_spec_drift_report,
    mark_stale_specs,
)
from nlreq.system_spec import SystemSpecRegistry


def test_spec_drift_report_passes_for_matching_source_hashes(tmp_path: Path) -> None:
    source = _write_source(tmp_path, "auth.py", "def authorize(): return True\n")
    manifest = _manifest({"auth.py": source})

    report = build_spec_drift_report(manifest, project_root=tmp_path)

    assert report.result == "passed"
    assert report.statuses[0].status == "fresh"


def test_spec_drift_report_blocks_changed_source_and_marks_registry_stale(
    tmp_path: Path,
) -> None:
    source = _write_source(tmp_path, "auth.py", "def authorize(): return True\n")
    manifest = _manifest({"auth.py": source})
    (tmp_path / "auth.py").write_text("def authorize(): return False\n")

    report = build_spec_drift_report(manifest, project_root=tmp_path)
    updated = mark_stale_specs(_registry(), report)

    assert report.result == "blocked"
    assert report.statuses[0].status == "stale"
    assert report.statuses[0].changed_paths == ["auth.py"]
    assert updated.specs[0].freshness == "stale"


def test_spec_drift_propagates_dependency_edges(tmp_path: Path) -> None:
    auth_hash = _write_source(tmp_path, "auth.py", "def authorize(): return True\n")
    api_hash = _write_source(tmp_path, "api.py", "def handler(): return authorize()\n")
    manifest = CodeSpecManifest.model_validate(
        {
            "schema_version": "0.1",
            "entries": [
                {
                    "module_id": "auth",
                    "source_paths": ["auth.py"],
                    "spec_ids": ["spec:auth"],
                    "recorded_source_hashes": {"auth.py": auth_hash},
                },
                {
                    "module_id": "api",
                    "source_paths": ["api.py"],
                    "spec_ids": ["spec:api"],
                    "dependency_module_ids": ["auth"],
                    "recorded_source_hashes": {"api.py": api_hash},
                },
            ],
        }
    )
    (tmp_path / "auth.py").write_text("def authorize(): return False\n")

    report = build_spec_drift_report(manifest, project_root=tmp_path)

    statuses = {status.module_id: status for status in report.statuses}
    assert statuses["auth"].status == "stale"
    assert statuses["api"].status == "stale"
    assert statuses["api"].stale_due_to_dependencies == ["auth"]


def test_spec_drift_reports_missing_source(tmp_path: Path) -> None:
    manifest = _manifest({"missing.py": "sha256:recorded"})

    report = build_spec_drift_report(manifest, project_root=tmp_path)

    assert report.result == "blocked"
    assert report.statuses[0].status == "missing_source"
    assert report.statuses[0].changed_paths == ["missing.py"]


def test_spec_drift_cli_writes_report_and_updated_registry(tmp_path: Path, capsys) -> None:
    source_hash = _write_source(tmp_path, "auth.py", "def authorize(): return True\n")
    manifest = _manifest({"auth.py": source_hash})
    (tmp_path / "auth.py").write_text("def authorize(): return False\n")
    manifest_path = tmp_path / "code-spec-manifest.json"
    registry_path = tmp_path / "registry.json"
    out = tmp_path / "drift.json"
    updated_out = tmp_path / "registry.updated.json"
    manifest_path.write_text(manifest.model_dump_json())
    registry_path.write_text(_registry().model_dump_json())

    exit_code = main(
        [
            "spec-drift",
            "--manifest",
            str(manifest_path),
            "--registry",
            str(registry_path),
            "--project-root",
            str(tmp_path),
            "--out",
            str(out),
            "--updated-registry-out",
            str(updated_out),
        ]
    )

    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Spec drift report:" in output
    assert read_json(out)["result"] == "blocked"
    assert read_json(updated_out)["specs"][0]["freshness"] == "stale"


def _write_source(tmp_path: Path, path: str, content: str) -> str:
    source = tmp_path / path
    source.write_text(content)
    return "sha256:" + hashlib.sha256(source.read_bytes()).hexdigest()


def _manifest(hashes: dict[str, str]) -> CodeSpecManifest:
    return CodeSpecManifest.model_validate(
        {
            "schema_version": "0.1",
            "entries": [
                {
                    "module_id": "auth",
                    "source_paths": list(hashes),
                    "spec_ids": ["spec:auth"],
                    "recorded_source_hashes": hashes,
                }
            ],
        }
    )


def _registry() -> SystemSpecRegistry:
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
                }
            ],
        }
    )
