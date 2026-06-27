from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .adoption import build_package_index, build_soft_gate_report, extract_requirement_ids
from .asyncapi_adapter import AsyncApiAdapter
from .command_adapter import CommandAdapter
from .continuous import load_attestation_run
from .gate import GatePolicy, GateWaiver, build_hard_gate_report
from .graphql_adapter import GraphQlAdapter
from .jsonschema_adapter import JsonSchemaAdapter
from .jsonutil import read_json, sha256_text, write_json
from .openapi_adapter import OpenApiAdapter
from .protobuf_adapter import ProtobufAdapter
from .python_adapter import PythonPackageAdapter
from .status import is_human_accepted
from .tla_adapter import TlaAdapter


AGENT_ARTIFACT_VERSION = "0.1"
AGENT_ROLES = {"specifier", "coder", "verifier", "reviewer"}


def build_agent_implementation_task(
    packages_dir: Path,
    *,
    requirement_ids: list[str],
    workflow_id: str | None = None,
    step_id: str | None = None,
    created_at: str | None = None,
    allowed_paths: list[str] | None = None,
    reviewer_constraints: list[str] | None = None,
    python_adapter: PythonPackageAdapter | None = None,
    openapi_adapter: OpenApiAdapter | None = None,
    command_adapter: CommandAdapter | None = None,
    tla_adapter: TlaAdapter | None = None,
    graphql_adapter: GraphQlAdapter | None = None,
    json_schema_adapter: JsonSchemaAdapter | None = None,
    asyncapi_adapter: AsyncApiAdapter | None = None,
    protobuf_adapter: ProtobufAdapter | None = None,
) -> dict[str, Any]:
    created_at = created_at or _utc_now()
    workflow_id = workflow_id or _workflow_id(created_at)
    step_id = step_id or "implementation-task"
    requirement_ids = _stable_unique(requirement_ids)
    package_index = build_package_index(
        packages_dir,
        python_adapter=python_adapter,
        openapi_adapter=openapi_adapter,
        command_adapter=command_adapter,
        tla_adapter=tla_adapter,
        graphql_adapter=graphql_adapter,
        json_schema_adapter=json_schema_adapter,
        asyncapi_adapter=asyncapi_adapter,
        protobuf_adapter=protobuf_adapter,
    )
    packages_by_id = _packages_by_id(package_index["packages"])
    packages = [
        _implementation_package_summary(packages_by_id[requirement_id])
        for requirement_id in requirement_ids
        if requirement_id in packages_by_id
    ]
    blockers = _implementation_task_blockers(requirement_ids, packages_by_id)
    return {
        "artifact_version": AGENT_ARTIFACT_VERSION,
        "artifact_kind": "agent_implementation_task",
        "workflow_id": workflow_id,
        "step_id": step_id,
        "created_at": created_at,
        "requirement_ids": requirement_ids,
        "ready": not blockers,
        "implementation_scope": {
            "allowed_paths": allowed_paths or [],
        },
        "constraints": {
            "reviewer": reviewer_constraints or [],
            "do_not_mutate_reviewed_package_artifacts": True,
            "do_not_weaken_requirements_without_review": True,
        },
        "packages": packages,
        "blockers": blockers,
        "package_index": {
            "index_version": package_index["index_version"],
            "packages_root": package_index["packages_root"],
            "summary": package_index["summary"],
        },
    }


def build_agent_verifier_handoff(
    packages_dir: Path,
    *,
    requirement_ids: list[str],
    workflow_id: str | None = None,
    step_id: str | None = None,
    created_at: str | None = None,
    python_adapter: PythonPackageAdapter | None = None,
    openapi_adapter: OpenApiAdapter | None = None,
    command_adapter: CommandAdapter | None = None,
    tla_adapter: TlaAdapter | None = None,
    graphql_adapter: GraphQlAdapter | None = None,
    json_schema_adapter: JsonSchemaAdapter | None = None,
    asyncapi_adapter: AsyncApiAdapter | None = None,
    protobuf_adapter: ProtobufAdapter | None = None,
    hard_gate_policy: GatePolicy | None = None,
    hard_gate_waivers: list[GateWaiver] | None = None,
    changed_paths: list[str] | None = None,
    continuous_run: dict[str, Any] | None = None,
) -> dict[str, Any]:
    created_at = created_at or _utc_now()
    workflow_id = workflow_id or _workflow_id(created_at)
    step_id = step_id or "verifier-handoff"
    requirement_ids = _stable_unique(requirement_ids)
    soft_gate = build_soft_gate_report(
        packages_dir,
        requirement_ids=requirement_ids,
        python_adapter=python_adapter,
        openapi_adapter=openapi_adapter,
        command_adapter=command_adapter,
        tla_adapter=tla_adapter,
        graphql_adapter=graphql_adapter,
        json_schema_adapter=json_schema_adapter,
        asyncapi_adapter=asyncapi_adapter,
        protobuf_adapter=protobuf_adapter,
    )
    hard_gate = None
    if hard_gate_policy is not None:
        hard_gate = build_hard_gate_report(
            packages_dir,
            requirement_ids=requirement_ids,
            policy=hard_gate_policy,
            waivers=hard_gate_waivers or [],
            changed_paths=changed_paths or [],
            python_adapter=python_adapter,
            openapi_adapter=openapi_adapter,
            command_adapter=command_adapter,
            tla_adapter=tla_adapter,
            graphql_adapter=graphql_adapter,
            json_schema_adapter=json_schema_adapter,
            asyncapi_adapter=asyncapi_adapter,
            protobuf_adapter=protobuf_adapter,
        )
    package_index = soft_gate["package_index"]
    packages_by_id = _packages_by_id(package_index["packages"])
    packages = [
        _verifier_package_summary(packages_by_id[requirement_id], packages_dir)
        for requirement_id in requirement_ids
        if requirement_id in packages_by_id
    ]
    findings = [
        *[_agent_finding("soft_gate", finding) for finding in soft_gate["findings"]],
        *(
            [_agent_finding("hard_gate", finding) for finding in hard_gate["findings"]]
            if hard_gate
            else []
        ),
        *(
            [
                _agent_finding("continuous_attestation", finding)
                for finding in continuous_run.get("findings", [])
            ]
            if continuous_run
            else []
        ),
    ]
    retry_payloads = _retry_payloads(
        requirement_ids=requirement_ids,
        packages_by_id=packages_by_id,
        packages_dir=packages_dir,
        findings=findings,
    )
    blocker_count = sum(1 for finding in findings if finding["severity"] in {"blocker", "error"})
    return {
        "artifact_version": AGENT_ARTIFACT_VERSION,
        "artifact_kind": "agent_verifier_handoff",
        "workflow_id": workflow_id,
        "step_id": step_id,
        "created_at": created_at,
        "requirement_ids": requirement_ids,
        "result": "blocked" if blocker_count else "pass",
        "summary": {
            "packages": len(packages),
            "findings": len(findings),
            "blocking_findings": blocker_count,
            "retry_payloads": len(retry_payloads),
        },
        "packages": packages,
        "gate_reports": {
            "soft_gate": _gate_summary(soft_gate),
            "hard_gate": _gate_summary(hard_gate) if hard_gate else None,
        },
        "continuous_attestation": _continuous_summary(continuous_run),
        "findings": findings,
        "retry_payloads": retry_payloads,
        "review_handoff": {
            "human_review_required": bool(blocker_count or retry_payloads),
            "focus": _review_focus(findings, retry_payloads),
        },
    }


def agent_pr_comment_markdown(handoff: dict[str, Any]) -> str:
    summary = handoff["summary"]
    lines = [
        "# NLReq Agent Verification Handoff",
        "",
        f"Workflow: `{handoff['workflow_id']}`",
        f"Step: `{handoff['step_id']}`",
        f"Result: `{handoff['result']}`",
        "",
        "## Summary",
        "",
        f"- Packages: {summary['packages']}",
        f"- Findings: {summary['findings']}",
        f"- Blocking findings: {summary['blocking_findings']}",
        f"- Retry payloads: {summary['retry_payloads']}",
        "",
        "## Findings",
        "",
    ]
    findings = handoff.get("findings", [])
    if not findings:
        lines.append("No findings.")
    else:
        lines.extend(
            [
                "| Source | Severity | Category | Requirement | Message |",
                "|---|---|---|---|---|",
            ]
        )
        for finding in findings:
            lines.append(
                "| {source} | {severity} | {category} | {requirement_id} | {message} |".format(
                    source=finding["source"],
                    severity=finding["severity"],
                    category=finding["category"],
                    requirement_id=finding.get("requirement_id") or "-",
                    message=_escape_markdown_table(finding["message"]),
                )
            )
    lines.extend(["", "## Retry Payloads", ""])
    retry_payloads = handoff.get("retry_payloads", [])
    if not retry_payloads:
        lines.append("No retry payloads.")
    else:
        for retry in retry_payloads:
            lines.extend(
                [
                    f"### {retry['requirement_id']}",
                    "",
                    f"- Reason: {retry['reason']}",
                    f"- Package: `{retry['package_path']}`",
                    f"- Failed checks: {', '.join(retry['failed_checks']) or '-'}",
                    "",
                ]
            )
    return "\n".join(lines) + "\n"


def build_agent_audit_entry(
    *,
    workflow_id: str,
    step_id: str,
    agent_role: str,
    tool: str,
    input_packages: list[dict[str, Any]] | None = None,
    output_artifact_paths: Iterable[Path] = (),
    git_ref: str | None = None,
    decision: dict[str, Any] | None = None,
    human_approvals: list[dict[str, Any]] | None = None,
    timestamp: str | None = None,
) -> dict[str, Any]:
    if agent_role not in AGENT_ROLES:
        raise ValueError(f"unsupported agent role: {agent_role}")
    return {
        "artifact_version": AGENT_ARTIFACT_VERSION,
        "artifact_kind": "agent_audit_entry",
        "workflow_id": workflow_id,
        "step_id": step_id,
        "agent_role": agent_role,
        "tool": tool,
        "timestamp": timestamp or _utc_now(),
        "git_ref": git_ref,
        "input_packages": input_packages or [],
        "output_artifacts": [
            _artifact_ref(path) for path in output_artifact_paths if Path(path).is_file()
        ],
        "decision": decision or {},
        "human_approvals": human_approvals or [],
    }


def append_agent_audit_entry(log_path: Path, entry: dict[str, Any]) -> list[dict[str, Any]]:
    if log_path.exists():
        existing = read_json(log_path)
        if not isinstance(existing, list):
            raise ValueError("agent audit log must be a JSON list")
        entries = existing
    else:
        entries = []
    entries.append(entry)
    write_json(log_path, entries)
    return entries


def package_input_refs(package_paths: Iterable[Path]) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for package_path in package_paths:
        package_path = Path(package_path)
        requirement_ir = package_path / "requirement.ir.json"
        status = package_path / "status.json"
        evidence = package_path / "evidence.json"
        refs.append(
            {
                "path": package_path.as_posix(),
                "requirement_id": _requirement_id_from_package(package_path),
                "hashes": {
                    **({"requirement_ir": sha256_text(requirement_ir.read_text())} if requirement_ir.is_file() else {}),
                    **({"status": sha256_text(status.read_text())} if status.is_file() else {}),
                    **({"evidence": sha256_text(evidence.read_text())} if evidence.is_file() else {}),
                },
            }
        )
    return refs


def requirement_ids_from_inputs(requirement_ids: list[str], reference_texts: list[str]) -> list[str]:
    values = list(requirement_ids)
    for text in reference_texts:
        values.extend(extract_requirement_ids(text))
    return _stable_unique(values)


def load_continuous_run(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    return load_attestation_run(path)


def _requirement_id_from_package(package_path: Path) -> str | None:
    try:
        value = read_json(package_path / "requirement.ir.json")
    except (OSError, ValueError):
        return None
    if isinstance(value, dict) and isinstance(value.get("requirement_id"), str):
        return value["requirement_id"]
    return None


def _implementation_task_blockers(
    requirement_ids: list[str], packages_by_id: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    blockers: list[dict[str, Any]] = []
    for requirement_id in requirement_ids:
        package = packages_by_id.get(requirement_id)
        if package is None:
            blockers.append(
                _blocker(
                    "missing_package",
                    requirement_id,
                    "referenced requirement package was not found",
                )
            )
            continue
        if package["validation_status"] != "valid":
            blockers.append(
                _blocker(
                    "package_validity",
                    requirement_id,
                    "; ".join(package["validation_errors"]) or "package validation failed",
                )
            )
        if not is_human_accepted(package["status"]):
            blockers.append(
                _blocker(
                    "status",
                    requirement_id,
                    f"package status is {package['status']}",
                )
            )
        # CATEGORY-2 REVIEW CHECK — AC1 BASELINE (ADR 0206 §2): gates on ``decision == "approved"``
        # not ``is_real_human_review``. Tightening would block every default package (each carries
        # the fabricated package-builder approval) — a direct AC1 violation. The machine-pin path
        # is protected at the provenance axis (``validate_package`` refuses a machine-pinned package
        # with an ``approved`` review), not here. See ``gate.py`` for the full rationale.
        if package["review"]["decision"] != "approved":
            blockers.append(
                _blocker(
                    "pending_review",
                    requirement_id,
                    "package review decision is not approved",
                )
            )
    return blockers


def _implementation_package_summary(package: dict[str, Any]) -> dict[str, Any]:
    return {
        "requirement_id": package["requirement_id"],
        "path": package["path"],
        "title": package["title"],
        "adapter": package["adapter"],
        "status": package["status"],
        "validation_status": package["validation_status"],
        "review": package["review"],
        "required_evidence": package["evidence"]["claims"],
        "assumptions": _read_assumptions(Path(package["path"])),
        "artifacts": package["artifacts"],
    }


def _verifier_package_summary(package: dict[str, Any], packages_dir: Path) -> dict[str, Any]:
    package_path = Path(package["path"])
    if not package_path.is_absolute():
        package_path = Path.cwd() / package_path
    counterexamples = _read_json_list(package_path / "counterexamples.json")
    normalized_traces = _read_json_list(package_path / "normalized-traces.json")
    return {
        "requirement_id": package["requirement_id"],
        "path": package["path"],
        "adapter": package["adapter"],
        "status": package["status"],
        "validation_status": package["validation_status"],
        "evidence": package["evidence"],
        "artifacts": package["artifacts"],
        "counterexamples": counterexamples,
        "normalized_traces": normalized_traces,
    }


def _retry_payloads(
    *,
    requirement_ids: list[str],
    packages_by_id: dict[str, dict[str, Any]],
    packages_dir: Path,
    findings: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    findings_by_requirement: dict[str, list[dict[str, Any]]] = {}
    for finding in findings:
        requirement_id = finding.get("requirement_id")
        if isinstance(requirement_id, str):
            findings_by_requirement.setdefault(requirement_id, []).append(finding)
    for requirement_id in requirement_ids:
        package = packages_by_id.get(requirement_id)
        if package is None:
            payloads.append(
                {
                    "requirement_id": requirement_id,
                    "package_path": None,
                    "reason": "requirement package missing",
                    "failed_checks": [],
                    "backend_results": [],
                    "counterexamples": [],
                    "findings": findings_by_requirement.get(requirement_id, []),
                    "instructions": [
                        "Create or select a reviewed requirement package before implementation."
                    ],
                }
            )
            continue
        evidence = package["evidence"]
        package_findings = findings_by_requirement.get(requirement_id, [])
        should_retry = (
            package["validation_status"] != "valid"
            or bool(evidence["failed_checks"])
            or bool(evidence["unsupported_claims"])
            or bool(package_findings)
            or not is_human_accepted(package["status"])
        )
        if not should_retry:
            continue
        package_path = Path(package["path"])
        if not package_path.is_absolute():
            package_path = Path.cwd() / package_path
        payloads.append(
            {
                "requirement_id": requirement_id,
                "package_path": package["path"],
                "reason": _retry_reason(package, package_findings),
                "failed_checks": evidence["failed_checks"],
                "backend_results": _backend_results(package_path),
                "counterexamples": _read_json_list(package_path / "counterexamples.json"),
                "findings": package_findings,
                "instructions": [
                    "Address deterministic check failures without weakening reviewed requirements.",
                    "Do not edit reviewed package artifacts in place.",
                    "Escalate unsupported or ambiguous requirements to the specifier and reviewer.",
                ],
            }
        )
    return payloads


def _retry_reason(package: dict[str, Any], findings: list[dict[str, Any]]) -> str:
    if package["validation_status"] != "valid":
        return "package validation failed"
    if package["evidence"]["failed_checks"]:
        return "evidence checks failed"
    if package["evidence"]["unsupported_claims"]:
        return "unsupported claims require specification review"
    if not is_human_accepted(package["status"]):
        return f"package status is {package['status']}"
    if findings:
        return "gate or continuous attestation findings require attention"
    return "verification retry required"


def _backend_results(package_path: Path) -> list[dict[str, Any]]:
    results = _read_json_list(package_path / "adapter-results.json")
    if results:
        return results
    evidence = read_json(package_path / "evidence.json")
    backend_results: list[dict[str, Any]] = []
    for claim in evidence.get("claims", []):
        if isinstance(claim, dict):
            for result in claim.get("backend_results", []):
                if isinstance(result, dict):
                    backend_results.append(result)
    return backend_results


def _read_assumptions(package_path: Path) -> list[dict[str, Any]]:
    return _read_json_list(package_path / "assumptions.json")


def _read_json_list(path: Path) -> list[dict[str, Any]]:
    try:
        value = read_json(path)
    except (OSError, ValueError):
        return []
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _agent_finding(source: str, finding: dict[str, Any]) -> dict[str, Any]:
    severity = str(finding.get("severity") or finding.get("enforcement") or "warning")
    if severity == "blocking":
        severity = "blocker"
    return {
        "source": source,
        "severity": severity,
        "category": str(finding.get("category", "unknown")),
        "requirement_id": finding.get("requirement_id"),
        "path": str(finding.get("path", "")),
        "message": str(finding.get("message", "")),
    }


def _gate_summary(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "mode": report["mode"],
        "result": report["result"],
        "summary": report["summary"],
        "references": report["references"],
    }


def _continuous_summary(report: dict[str, Any] | None) -> dict[str, Any] | None:
    if report is None:
        return None
    return {
        "run_id": report["run_id"],
        "result": report["result"],
        "summary": report["summary"],
    }


def _review_focus(
    findings: list[dict[str, Any]], retry_payloads: list[dict[str, Any]]
) -> list[str]:
    focus: list[str] = []
    categories = sorted({finding["category"] for finding in findings})
    if categories:
        focus.append("Findings: " + ", ".join(categories))
    if retry_payloads:
        focus.append(
            "Retry requirements: "
            + ", ".join(payload["requirement_id"] for payload in retry_payloads)
        )
    if not focus:
        focus.append("Review package evidence and implementation scope.")
    return focus


def _artifact_ref(path: Path) -> dict[str, Any]:
    path = Path(path)
    return {
        "path": path.as_posix(),
        "hash": sha256_text(path.read_text()),
    }


def _blocker(category: str, requirement_id: str, message: str) -> dict[str, Any]:
    return {
        "category": category,
        "requirement_id": requirement_id,
        "message": message,
    }


def _packages_by_id(packages: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        package["requirement_id"]: package
        for package in packages
        if package.get("requirement_id")
    }


def _stable_unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        if value not in seen:
            unique.append(value)
            seen.add(value)
    return unique


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _workflow_id(created_at: str) -> str:
    safe = created_at.replace(":", "").replace("-", "").replace("+", "").replace("Z", "")
    return f"WF-{safe}"


def _escape_markdown_table(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")
