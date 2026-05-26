import json
from pathlib import Path

from nlreq.cli import main
from nlreq.continuous import build_attestation_run, continuous_attestation_markdown
from nlreq.jsonutil import read_json
from nlreq.package import build_package


FIXTURES = Path(__file__).parent / "fixtures" / "requirements"


def test_build_attestation_run_reports_package_freshness(tmp_path: Path) -> None:
    package_root = tmp_path / "requirements"
    build_package(
        controlled_text=(FIXTURES / "authorization_precondition.nlreq").read_text(),
        output_dir=package_root / "REQ-AUTH-001",
        requirement_id="REQ-AUTH-001",
        title="Unauthorized operation is rejected before state changes",
        claim_kind="authorization_precondition",
    )

    report = build_attestation_run(
        package_root,
        trigger="schedule",
        run_id="RUN-PHASE-8-001",
        timestamp="2026-06-01T00:00:00Z",
        repo_ref="refs/heads/main@abc123",
    )

    assert report["run_version"] == "0.1"
    assert report["mode"] == "continuous_attestation"
    assert report["result"] == "report_only"
    assert report["summary"]["total"] == 1
    assert report["summary"]["valid"] == 1
    assert report["summary"]["findings"] == 0
    assert report["package_freshness"][0]["requirement_id"] == "REQ-AUTH-001"
    assert report["package_freshness"][0]["review_age_days"] == 6


def test_attestation_run_detects_status_regression_from_previous_run(tmp_path: Path) -> None:
    package_root = tmp_path / "requirements"
    build_package(
        controlled_text=(FIXTURES / "authorization_precondition.nlreq").read_text(),
        output_dir=package_root / "REQ-AUTH-001",
        requirement_id="REQ-AUTH-001",
        title="Unauthorized operation is rejected before state changes",
        claim_kind="authorization_precondition",
    )
    previous = build_attestation_run(
        package_root,
        run_id="RUN-PREVIOUS",
        timestamp="2026-06-01T00:00:00Z",
    )
    build_package(
        controlled_text=(FIXTURES / "unbound_symbol.nlreq").read_text(),
        output_dir=package_root / "REQ-AUTH-001",
        requirement_id="REQ-AUTH-001",
        title="Unauthorized operation is rejected before state changes",
        claim_kind="authorization_precondition",
    )

    current = build_attestation_run(
        package_root,
        run_id="RUN-CURRENT",
        timestamp="2026-06-02T00:00:00Z",
        previous_run=previous,
    )

    assert any(delta["category"] == "status_regressed" for delta in current["deltas"])
    assert any(finding["category"] == "status_regressed" for finding in current["findings"])
    assert current["summary"]["error_findings"] >= 1


def test_attestation_run_ingests_normalized_trace_artifacts(tmp_path: Path) -> None:
    package_root = tmp_path / "requirements"
    build_package(
        controlled_text=(FIXTURES / "authorization_precondition.nlreq").read_text(),
        output_dir=package_root / "REQ-AUTH-001",
        requirement_id="REQ-AUTH-001",
        title="Unauthorized operation is rejected before state changes",
        claim_kind="authorization_precondition",
    )
    trace_artifact = tmp_path / "normalized-traces.json"
    trace_artifact.write_text(
        json.dumps(
            [
                {
                    "trace_id": "TRACE-REQ-AUTH-001",
                    "adapter_id": "generic",
                    "source_hash": "sha256:trace-source",
                    "events": [
                        {
                            "event_id": "evt-1",
                            "timestamp": "2026-06-01T00:00:00Z",
                            "actor": "alice",
                            "action": "operation",
                        }
                    ],
                    "metadata": {
                        "requirement_ids": ["REQ-AUTH-001"],
                        "environment": "staging",
                        "capture_window": {
                            "start": "2026-06-01T00:00:00Z",
                            "end": "2026-06-01T01:00:00Z",
                        },
                        "redaction": {"status": "redacted"},
                    },
                }
            ],
            indent=2,
        )
    )

    report = build_attestation_run(
        package_root,
        run_id="RUN-TRACE",
        timestamp="2026-06-01T02:00:00Z",
        trace_artifact_paths=[trace_artifact],
    )

    assert report["summary"]["trace_artifacts"] == 1
    assert report["summary"]["traces"] == 1
    assert report["trace_artifacts"]["artifacts"][0]["status"] == "valid"
    assert report["trace_artifacts"]["artifacts"][0]["traces"][0]["known_requirement_ids"] == [
        "REQ-AUTH-001"
    ]
    assert not any(finding["category"].startswith("trace_") for finding in report["findings"])


def test_attestation_run_reports_trace_provenance_findings(tmp_path: Path) -> None:
    package_root = tmp_path / "requirements"
    build_package(
        controlled_text=(FIXTURES / "authorization_precondition.nlreq").read_text(),
        output_dir=package_root / "REQ-AUTH-001",
        requirement_id="REQ-AUTH-001",
        title="Unauthorized operation is rejected before state changes",
        claim_kind="authorization_precondition",
    )
    trace_artifact = tmp_path / "bad-trace.json"
    trace_artifact.write_text(
        json.dumps(
            [
                {
                    "trace_id": "TRACE-UNKNOWN",
                    "adapter_id": "openapi",
                    "source_hash": "sha256:trace-source",
                    "events": [
                        {
                            "event_id": "evt-1",
                            "timestamp": "2026-06-01T00:00:00Z",
                            "action": "operation",
                        }
                    ],
                    "metadata": {"requirement_ids": ["REQ-UNKNOWN-001"]},
                }
            ]
        )
    )

    report = build_attestation_run(
        package_root,
        run_id="RUN-BAD-TRACE",
        timestamp="2026-06-01T02:00:00Z",
        trace_artifact_paths=[trace_artifact],
    )

    categories = {finding["category"] for finding in report["findings"]}
    assert "trace_unknown_requirement" in categories
    assert "trace_redaction_missing" in categories


def test_continuous_attestation_cli_writes_json_and_markdown(
    tmp_path: Path, capsys
) -> None:
    package_root = tmp_path / "requirements"
    out = tmp_path / "continuous.json"
    markdown_out = tmp_path / "continuous.md"
    build_package(
        controlled_text=(FIXTURES / "authorization_precondition.nlreq").read_text(),
        output_dir=package_root / "REQ-AUTH-001",
        requirement_id="REQ-AUTH-001",
        title="Unauthorized operation is rejected before state changes",
        claim_kind="authorization_precondition",
    )

    exit_code = main(
        [
            "continuous-attestation",
            str(package_root),
            "--trigger",
            "schedule",
            "--run-id",
            "RUN-CLI-001",
            "--timestamp",
            "2026-06-01T00:00:00Z",
            "--out",
            str(out),
            "--markdown-out",
            str(markdown_out),
        ]
    )
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Continuous attestation report:" in output
    assert "Continuous attestation markdown:" in output
    assert read_json(out)["run_id"] == "RUN-CLI-001"
    assert "# NLReq Continuous Attestation Report" in markdown_out.read_text()


def test_continuous_attestation_markdown_renders_findings(tmp_path: Path) -> None:
    package_root = tmp_path / "requirements"
    build_package(
        controlled_text=(FIXTURES / "unbound_symbol.nlreq").read_text(),
        output_dir=package_root / "REQ-REFUSED-UNBOUND-001",
        requirement_id="REQ-REFUSED-UNBOUND-001",
        title="Unbound operator example",
        claim_kind="authorization_precondition",
    )

    report = build_attestation_run(
        package_root,
        run_id="RUN-MD",
        timestamp="2026-06-01T00:00:00Z",
    )

    markdown = continuous_attestation_markdown(report)

    assert "| warning | status | REQ-REFUSED-UNBOUND-001 |" in markdown
