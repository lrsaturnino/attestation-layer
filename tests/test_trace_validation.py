import json
from pathlib import Path

from nlreq.cli import main
from nlreq.continuous import build_attestation_run
from nlreq.jsonutil import read_json
from nlreq.package import build_package
from nlreq.trace_validation import build_trace_validation_report, trace_validation_markdown


FIXTURES = Path(__file__).parent / "fixtures" / "requirements"


def test_trace_validation_accepts_observed_auth_rejection(tmp_path: Path) -> None:
    package_root = _package_root(tmp_path)
    trace_artifact = tmp_path / "valid-trace.json"
    _write_trace(trace_artifact)

    report = build_trace_validation_report(
        package_root,
        trace_artifact_paths=[trace_artifact],
        requirement_ids=["REQ-AUTH-001"],
    )

    assert report["summary"]["results"] == 1
    assert report["summary"]["valid"] == 1
    result = report["results"][0]
    assert result["status"] == "valid"
    assert result["evidence_level"] == "TRACE_VALIDATED"
    assert result["details"]["validator_id"] == "authorization-before-state-change"
    assert result["details"]["forbidden_events_absent"] == ["state_change"]
    # The TRACE_VALIDATED claim is backed by the observed→fragment mapping it validated.
    trace_mapping = result["details"]["trace_mapping"]
    assert trace_mapping["validator_id"] == "authorization-before-state-change"
    assert trace_mapping["fragment"] == {"forbidden_events_absent": ["state_change"]}
    assert "request_received" in trace_mapping["observed_events"]


def test_trace_validation_records_counterexample_for_forbidden_event(tmp_path: Path) -> None:
    package_root = _package_root(tmp_path)
    trace_artifact = tmp_path / "invalid-trace.json"
    _write_trace(trace_artifact, actions=["request_received", "request_rejected", "state_change"])

    report = build_trace_validation_report(
        package_root,
        trace_artifact_paths=[trace_artifact],
        requirement_ids=["REQ-AUTH-001"],
    )

    assert report["summary"]["invalid"] == 1
    assert report["summary"]["counterexamples"] == 1
    assert report["counterexamples"][0]["backend"] == "trace"
    assert report["findings"][0]["category"] == "trace_validation_counterexample"


def test_trace_validation_requires_acceptable_redaction(tmp_path: Path) -> None:
    package_root = _package_root(tmp_path)
    trace_artifact = tmp_path / "unredacted-trace.json"
    _write_trace(trace_artifact, redaction_status="unredacted")

    report = build_trace_validation_report(
        package_root,
        trace_artifact_paths=[trace_artifact],
        requirement_ids=["REQ-AUTH-001"],
    )

    assert report["summary"]["needs_review"] == 1
    assert report["findings"][0]["category"] == "trace_validation_needs_review"
    # A redaction-blocked trace validated nothing, so the result claims no evidence level rather
    # than over-claiming TRACE_VALIDATED (dumped with exclude_none, so the key is absent).
    assert "evidence_level" not in report["results"][0]


def test_trace_validate_cli_writes_json_and_markdown(tmp_path: Path, capsys) -> None:
    package_root = _package_root(tmp_path)
    trace_artifact = tmp_path / "valid-trace.json"
    out = tmp_path / "trace-validation.json"
    markdown_out = tmp_path / "trace-validation.md"
    _write_trace(trace_artifact)

    exit_code = main(
        [
            "trace-validate",
            str(package_root),
            "--requirement-id",
            "REQ-AUTH-001",
            "--trace-artifact",
            str(trace_artifact),
            "--out",
            str(out),
            "--markdown-out",
            str(markdown_out),
        ]
    )

    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Trace validation report:" in output
    assert read_json(out)["summary"]["valid"] == 1
    assert "# NLReq Trace Validation Report" in markdown_out.read_text()


def test_continuous_attestation_can_include_trace_validation(tmp_path: Path) -> None:
    package_root = _package_root(tmp_path)
    trace_artifact = tmp_path / "invalid-trace.json"
    _write_trace(trace_artifact, actions=["request_received", "state_change"])

    report = build_attestation_run(
        package_root,
        run_id="RUN-TRACE-VALIDATION",
        timestamp="2026-06-01T00:00:00Z",
        trace_artifact_paths=[trace_artifact],
        trace_validation=True,
    )

    assert report["summary"]["trace_validation_results"] == 1
    assert report["trace_validation"]["summary"]["counterexamples"] == 1
    assert any(
        finding["category"] == "trace_validation_counterexample"
        for finding in report["findings"]
    )


def test_trace_validation_markdown_renders_results(tmp_path: Path) -> None:
    package_root = _package_root(tmp_path)
    trace_artifact = tmp_path / "valid-trace.json"
    _write_trace(trace_artifact)
    report = build_trace_validation_report(
        package_root,
        trace_artifact_paths=[trace_artifact],
    )

    markdown = trace_validation_markdown(report)

    assert "| valid | REQ-AUTH-001 | TRACE-REQ-AUTH-001 |" in markdown


def _package_root(tmp_path: Path) -> Path:
    package_root = tmp_path / "requirements"
    build_package(
        controlled_text=(FIXTURES / "authorization_precondition.nlreq").read_text(),
        output_dir=package_root / "REQ-AUTH-001",
        requirement_id="REQ-AUTH-001",
        title="Unauthorized operation is rejected before state changes",
        claim_kind="authorization_precondition",
    )
    return package_root


def _write_trace(
    path: Path,
    *,
    actions: list[str] | None = None,
    redaction_status: str = "redacted",
) -> None:
    actions = actions or ["request_received", "authorization_failed", "request_rejected"]
    path.write_text(
        json.dumps(
            [
                {
                    "trace_id": "TRACE-REQ-AUTH-001",
                    "adapter_id": "generic",
                    "source_hash": "sha256:trace-source",
                    "events": [
                        {
                            "event_id": f"evt-{index}",
                            "timestamp": f"2026-06-01T00:00:0{index}Z",
                            "action": action,
                        }
                        for index, action in enumerate(actions, start=1)
                    ],
                    "metadata": {
                        "requirement_ids": ["REQ-AUTH-001"],
                        "environment": "staging",
                        "capture_window": {
                            "start": "2026-06-01T00:00:00Z",
                            "end": "2026-06-01T00:01:00Z",
                        },
                        "redaction": {"status": redaction_status},
                    },
                }
            ],
            indent=2,
        )
    )
