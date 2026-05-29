from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Any, Iterable

from pydantic import ValidationError

from .adoption import ARTIFACT_FILES, build_package_index
from .command_adapter import CommandAdapter
from .graphql_adapter import GraphQlAdapter
from .jsonutil import read_json
from .models import NormalizedTraceArtifact
from .openapi_adapter import OpenApiAdapter
from .python_adapter import PythonPackageAdapter
from .trace_validation import build_trace_validation_report
from .tla_adapter import TlaAdapter


ATTESTATION_RUN_VERSION = "0.1"
TRIGGER_TYPES = {"manual", "schedule", "webhook", "release"}


def build_attestation_run(
    packages_dir: Path,
    *,
    trigger: str = "manual",
    run_id: str | None = None,
    timestamp: str | None = None,
    repo_ref: str | None = None,
    python_adapter: PythonPackageAdapter | None = None,
    openapi_adapter: OpenApiAdapter | None = None,
    command_adapter: CommandAdapter | None = None,
    tla_adapter: TlaAdapter | None = None,
    graphql_adapter: GraphQlAdapter | None = None,
    trace_artifact_paths: Iterable[Path] = (),
    trace_validation: bool = False,
    previous_run: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if trigger not in TRIGGER_TYPES:
        raise ValueError(f"unsupported continuous attestation trigger: {trigger}")
    trace_artifact_paths = tuple(trace_artifact_paths)
    timestamp = timestamp or _utc_now()
    run_id = run_id or _run_id_from_timestamp(timestamp)
    package_index = build_package_index(
        packages_dir,
        python_adapter=python_adapter,
        openapi_adapter=openapi_adapter,
        command_adapter=command_adapter,
        tla_adapter=tla_adapter,
        graphql_adapter=graphql_adapter,
    )
    packages_by_id = {
        package["requirement_id"]: package
        for package in package_index["packages"]
        if package["requirement_id"]
    }
    package_freshness = [
        _package_freshness(package, timestamp) for package in package_index["packages"]
    ]
    trace_summary, trace_findings = _trace_report(trace_artifact_paths, packages_by_id)
    trace_validation_report = (
        build_trace_validation_report(
            packages_dir,
            trace_artifact_paths=trace_artifact_paths,
        )
        if trace_validation
        else None
    )
    deltas = _deltas_from_previous(previous_run, package_index)
    findings = [
        *_package_findings(package_index["packages"]),
        *trace_findings,
        *(trace_validation_report["findings"] if trace_validation_report else []),
        *_findings_for_deltas(deltas),
    ]
    return {
        "run_version": ATTESTATION_RUN_VERSION,
        "mode": "continuous_attestation",
        "result": "report_only",
        "run_id": run_id,
        "trigger": trigger,
        "timestamp": timestamp,
        "repo_ref": repo_ref,
        "packages_root": packages_dir.as_posix(),
        "adapter_config": _adapter_config(
            python_adapter=python_adapter,
            openapi_adapter=openapi_adapter,
            command_adapter=command_adapter,
            tla_adapter=tla_adapter,
            graphql_adapter=graphql_adapter,
        ),
        "summary": {
            **package_index["summary"],
            "findings": len(findings),
            "error_findings": sum(1 for finding in findings if finding["severity"] == "error"),
            "warning_findings": sum(
                1 for finding in findings if finding["severity"] == "warning"
            ),
            "trace_artifacts": trace_summary["artifact_count"],
            "traces": trace_summary["trace_count"],
            "trace_validation_results": trace_validation_report["summary"]["results"]
            if trace_validation_report
            else 0,
            "deltas": len(deltas),
        },
        "findings": findings,
        "package_freshness": package_freshness,
        "trace_artifacts": trace_summary,
        "trace_validation": trace_validation_report,
        "deltas": deltas,
        "package_index": package_index,
    }


def load_attestation_run(path: Path) -> dict[str, Any]:
    value = read_json(path)
    if not isinstance(value, dict):
        raise ValueError("continuous attestation run must be a JSON object")
    if value.get("run_version") != ATTESTATION_RUN_VERSION:
        raise ValueError(f"unsupported attestation run version: {value.get('run_version')}")
    return value


def continuous_attestation_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# NLReq Continuous Attestation Report",
        "",
        f"Run: `{report['run_id']}`",
        f"Trigger: `{report['trigger']}`",
        f"Result: `{report['result']}`",
        f"Timestamp: `{report['timestamp']}`",
        "",
        "## Summary",
        "",
        f"- Packages: {summary['total']}",
        f"- Valid packages: {summary['valid']}",
        f"- Invalid packages: {summary['invalid']}",
        f"- Validation skipped: {summary['validation_skipped']}",
        f"- Trace artifacts: {summary['trace_artifacts']}",
        f"- Traces: {summary['traces']}",
        f"- Trace validation results: {summary.get('trace_validation_results', 0)}",
        f"- Deltas: {summary['deltas']}",
        f"- Findings: {summary['findings']}",
        "",
        "## Findings",
        "",
    ]
    findings = report["findings"]
    if not findings:
        lines.append("No findings.")
    else:
        lines.extend(
            [
                "| Severity | Category | Requirement | Message |",
                "|---|---|---|---|",
            ]
        )
        for finding in findings:
            lines.append(
                "| {severity} | {category} | {requirement_id} | {message} |".format(
                    severity=finding["severity"],
                    category=finding["category"],
                    requirement_id=finding.get("requirement_id") or "-",
                    message=_escape_markdown_table(finding["message"]),
                )
            )
    return "\n".join(lines) + "\n"


def _package_findings(packages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for package in packages:
        requirement_id = package["requirement_id"]
        path = package["path"]
        validation_status = package["validation_status"]
        if validation_status == "invalid":
            message = "; ".join(package["validation_errors"]) or "package validation failed"
            findings.append(
                _finding(
                    "error",
                    _validation_category(message),
                    requirement_id,
                    path,
                    message,
                )
            )
        if validation_status == "skipped":
            findings.append(
                _finding(
                    "warning",
                    "package_validity",
                    requirement_id,
                    path,
                    "; ".join(package["validation_errors"]),
                )
            )
        evidence = package["evidence"]
        if evidence["failed_checks"]:
            findings.append(
                _finding(
                    "error",
                    "failed_checks",
                    requirement_id,
                    path,
                    "failed checks: " + ", ".join(evidence["failed_checks"]),
                )
            )
        if evidence["unsupported_claims"]:
            findings.append(
                _finding(
                    "warning",
                    "unsupported_claims",
                    requirement_id,
                    path,
                    "unsupported claims: " + ", ".join(evidence["unsupported_claims"]),
                )
            )
        if evidence["timeouts"]:
            findings.append(
                _finding(
                    "error",
                    "timeouts",
                    requirement_id,
                    path,
                    "timeouts: " + ", ".join(evidence["timeouts"]),
                )
            )
        if package["status"] and str(package["status"]).startswith("REFUSED"):
            findings.append(
                _finding(
                    "warning",
                    "status",
                    requirement_id,
                    path,
                    f"package status is {package['status']}",
                )
            )
    return findings


def _package_freshness(package: dict[str, Any], timestamp: str) -> dict[str, Any]:
    artifacts = package["artifacts"]
    missing_artifacts = [artifact for artifact in ARTIFACT_FILES if artifact not in artifacts]
    review_timestamp = package["review"]["timestamp"]
    return {
        "requirement_id": package["requirement_id"],
        "path": package["path"],
        "adapter": package["adapter"],
        "validation_status": package["validation_status"],
        "status": package["status"],
        "artifact_count": len(artifacts),
        "missing_artifacts": missing_artifacts,
        "review_timestamp": review_timestamp,
        "review_age_days": _age_days(review_timestamp, timestamp),
        "evidence_hash": artifacts.get("evidence.json"),
        "status_hash": artifacts.get("status.json"),
    }


def _trace_report(
    trace_artifact_paths: Iterable[Path],
    packages_by_id: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    artifacts: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []
    trace_count = 0
    for path in trace_artifact_paths:
        path = Path(path)
        try:
            artifact = NormalizedTraceArtifact.model_validate_json(path.read_text())
        except (OSError, ValidationError, ValueError) as exc:
            findings.append(
                _finding(
                    "error",
                    "invalid_trace_artifact",
                    None,
                    path.as_posix(),
                    str(exc),
                )
            )
            artifacts.append(
                {
                    "path": path.as_posix(),
                    "status": "invalid",
                    "traces": [],
                    "trace_count": 0,
                }
            )
            continue
        traces: list[dict[str, Any]] = []
        for trace in artifact.root:
            trace_count += 1
            trace_summary = _trace_summary(trace, path, packages_by_id)
            traces.append(trace_summary)
            findings.extend(_trace_findings(trace_summary, packages_by_id))
        artifacts.append(
            {
                "path": path.as_posix(),
                "status": "valid",
                "trace_count": len(traces),
                "traces": traces,
            }
        )
    return {
        "artifact_count": len(artifacts),
        "trace_count": trace_count,
        "artifacts": artifacts,
    }, findings


def _trace_summary(trace: Any, path: Path, packages_by_id: dict[str, dict[str, Any]]) -> dict[str, Any]:
    requirement_ids = trace.metadata.get("requirement_ids", [])
    if not isinstance(requirement_ids, list):
        requirement_ids = []
    requirement_ids = [str(requirement_id) for requirement_id in requirement_ids]
    known_requirement_ids = [
        requirement_id for requirement_id in requirement_ids if requirement_id in packages_by_id
    ]
    unknown_requirement_ids = [
        requirement_id for requirement_id in requirement_ids if requirement_id not in packages_by_id
    ]
    redaction = trace.metadata.get("redaction", {})
    redaction_status = redaction.get("status") if isinstance(redaction, dict) else None
    return {
        "path": path.as_posix(),
        "trace_id": trace.trace_id,
        "adapter_id": trace.adapter_id,
        "source_hash": trace.source_hash,
        "event_count": len(trace.events),
        "requirement_ids": requirement_ids,
        "known_requirement_ids": known_requirement_ids,
        "unknown_requirement_ids": unknown_requirement_ids,
        "environment": trace.metadata.get("environment"),
        "capture_window": trace.metadata.get("capture_window"),
        "redaction_status": redaction_status,
    }


def _trace_findings(
    trace: dict[str, Any], packages_by_id: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    path = trace["path"]
    if not trace["requirement_ids"]:
        findings.append(
            _finding(
                "warning",
                "trace_missing_requirement_ids",
                None,
                path,
                f"trace {trace['trace_id']} has no requirement ids",
            )
        )
    for requirement_id in trace["unknown_requirement_ids"]:
        findings.append(
            _finding(
                "warning",
                "trace_unknown_requirement",
                requirement_id,
                path,
                f"trace {trace['trace_id']} references unknown requirement {requirement_id}",
            )
        )
    if trace["redaction_status"] not in {"redacted", "not_required"}:
        findings.append(
            _finding(
                "warning",
                "trace_redaction_missing",
                None,
                path,
                f"trace {trace['trace_id']} does not declare redaction status",
            )
        )
    for requirement_id in trace["known_requirement_ids"]:
        package_adapter = packages_by_id[requirement_id]["adapter"]
        if trace["adapter_id"] != package_adapter:
            findings.append(
                _finding(
                    "warning",
                    "trace_adapter_mismatch",
                    requirement_id,
                    path,
                    (
                        f"trace {trace['trace_id']} adapter {trace['adapter_id']} "
                        f"does not match package adapter {package_adapter}"
                    ),
                )
            )
    return findings


def _deltas_from_previous(
    previous_run: dict[str, Any] | None, current_index: dict[str, Any]
) -> list[dict[str, Any]]:
    if previous_run is None:
        return []
    previous_packages = _packages_by_id(previous_run.get("package_index", {}).get("packages", []))
    current_packages = _packages_by_id(current_index.get("packages", []))
    deltas: list[dict[str, Any]] = []
    for requirement_id in sorted(set(previous_packages) - set(current_packages)):
        deltas.append(
            {
                "category": "missing_package",
                "requirement_id": requirement_id,
                "previous": _package_delta_state(previous_packages[requirement_id]),
                "current": None,
            }
        )
    for requirement_id in sorted(set(current_packages) - set(previous_packages)):
        deltas.append(
            {
                "category": "new_package",
                "requirement_id": requirement_id,
                "previous": None,
                "current": _package_delta_state(current_packages[requirement_id]),
            }
        )
    for requirement_id in sorted(set(previous_packages).intersection(current_packages)):
        previous = previous_packages[requirement_id]
        current = current_packages[requirement_id]
        if _accepted(previous.get("status")) and not _accepted(current.get("status")):
            deltas.append(
                {
                    "category": "status_regressed",
                    "requirement_id": requirement_id,
                    "previous": _package_delta_state(previous),
                    "current": _package_delta_state(current),
                }
            )
        if previous.get("validation_status") == "valid" and current.get("validation_status") != "valid":
            deltas.append(
                {
                    "category": "validation_regressed",
                    "requirement_id": requirement_id,
                    "previous": _package_delta_state(previous),
                    "current": _package_delta_state(current),
                }
            )
        previous_evidence_hash = previous.get("artifacts", {}).get("evidence.json")
        current_evidence_hash = current.get("artifacts", {}).get("evidence.json")
        if previous_evidence_hash and current_evidence_hash and previous_evidence_hash != current_evidence_hash:
            deltas.append(
                {
                    "category": "evidence_changed",
                    "requirement_id": requirement_id,
                    "previous": _package_delta_state(previous),
                    "current": _package_delta_state(current),
                }
            )
    return deltas


def _findings_for_deltas(deltas: list[dict[str, Any]]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for delta in deltas:
        category = str(delta["category"])
        requirement_id = delta["requirement_id"]
        severity = "error" if category in {"status_regressed", "validation_regressed"} else "warning"
        findings.append(
            _finding(
                severity,
                category,
                requirement_id,
                "",
                _delta_message(delta),
            )
        )
    return findings


def _delta_message(delta: dict[str, Any]) -> str:
    category = delta["category"]
    requirement_id = delta["requirement_id"]
    if category == "missing_package":
        return f"requirement {requirement_id} was present in the previous run but is missing now"
    if category == "new_package":
        return f"requirement {requirement_id} is new in this run"
    previous = delta.get("previous") or {}
    current = delta.get("current") or {}
    if category == "status_regressed":
        return (
            f"requirement {requirement_id} status regressed from "
            f"{previous.get('status')} to {current.get('status')}"
        )
    if category == "validation_regressed":
        return (
            f"requirement {requirement_id} validation regressed from "
            f"{previous.get('validation_status')} to {current.get('validation_status')}"
        )
    return f"requirement {requirement_id} evidence changed since the previous run"


def _packages_by_id(packages: object) -> dict[str, dict[str, Any]]:
    if not isinstance(packages, list):
        return {}
    return {
        str(package["requirement_id"]): package
        for package in packages
        if isinstance(package, dict) and package.get("requirement_id")
    }


def _package_delta_state(package: dict[str, Any]) -> dict[str, Any]:
    return {
        "path": package.get("path"),
        "adapter": package.get("adapter"),
        "status": package.get("status"),
        "validation_status": package.get("validation_status"),
        "evidence_hash": package.get("artifacts", {}).get("evidence.json"),
        "status_hash": package.get("artifacts", {}).get("status.json"),
    }


def _adapter_config(
    *,
    python_adapter: PythonPackageAdapter | None,
    openapi_adapter: OpenApiAdapter | None,
    command_adapter: CommandAdapter | None,
    tla_adapter: TlaAdapter | None,
    graphql_adapter: GraphQlAdapter | None,
) -> dict[str, Any]:
    config: dict[str, Any] = {}
    if python_adapter is not None:
        config["python_package"] = {
            "package_root": python_adapter.package_root.as_posix(),
            "package_name": python_adapter.package_name,
            "project_root": python_adapter.project_root.as_posix(),
            "test_paths": [path.as_posix() for path in python_adapter.test_paths],
            "property_checks": python_adapter.property_checks,
        }
    if openapi_adapter is not None:
        config["openapi"] = {
            "document_path": openapi_adapter.document_path.as_posix(),
            "document_name": openapi_adapter.document_name,
            "document_hash": openapi_adapter.document_hash,
        }
    if command_adapter is not None:
        config["command"] = {
            "project_root": command_adapter.project_root.as_posix(),
            "checks": len(command_adapter.checks.checks),
        }
    if graphql_adapter is not None:
        config["graphql"] = {
            "schema_path": graphql_adapter.schema_path.as_posix(),
            "schema_name": graphql_adapter.schema_name,
            "schema_hash": graphql_adapter.schema_hash,
        }
    if tla_adapter is not None:
        config["tla"] = {
            "project_root": tla_adapter.project_root.as_posix(),
            "models": len(tla_adapter.config.models),
        }
    return config


def _finding(
    severity: str,
    category: str,
    requirement_id: str | None,
    path: str,
    message: str,
) -> dict[str, Any]:
    return {
        "severity": severity,
        "category": category,
        "requirement_id": requirement_id,
        "path": path,
        "message": message,
    }


def _validation_category(message: str) -> str:
    stale_markers = (
        "does not match",
        "hash",
        "stale",
        "evidence.json",
        "status.json",
        "verification-tasks.json",
        "review.json",
    )
    if any(marker in message for marker in stale_markers):
        return "stale_evidence"
    return "package_validity"


def _accepted(status: object) -> bool:
    return isinstance(status, str) and status.startswith("ACCEPTED")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _run_id_from_timestamp(timestamp: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9]+", "-", timestamp).strip("-")
    return f"RUN-{normalized}"


def _age_days(start: object, end: str) -> int | None:
    if not isinstance(start, str):
        return None
    try:
        start_dt = _parse_timestamp(start)
        end_dt = _parse_timestamp(end)
    except ValueError:
        return None
    return max((end_dt - start_dt).days, 0)


def _parse_timestamp(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _escape_markdown_table(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")
