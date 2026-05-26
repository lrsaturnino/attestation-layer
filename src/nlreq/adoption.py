from __future__ import annotations

from pathlib import Path
import re
from typing import Any

from pydantic import ValidationError

from .jsonutil import sha256_text
from .models import EvidenceObject, RequirementIR, ReviewArtifact, StatusDecision
from .package import validate_package
from .python_adapter import PythonPackageAdapter
from .python_package import validate_python_package


INDEX_VERSION = "0.1"
REPORT_VERSION = "0.1"
REQUIREMENT_ID_PATTERN = re.compile(r"\bREQ-[A-Z0-9][A-Z0-9-]*\b")
REVIEW_CHECKLIST_ITEMS = [
    ("controlled_form_matches_intent", "Controlled form matches original intent."),
    ("claim_shape_matches_controlled_form", "Claim shape matches controlled form."),
    ("source_spans_present", "Source spans are present."),
    ("assumptions_explicit", "Assumptions are explicit."),
    ("bindings_justified", "Bindings are deterministic or manually justified."),
    ("evidence_level_appropriate", "Required evidence level is appropriate."),
    ("unsupported_claims_hidden", "Unsupported claims are not hidden behind weaker evidence."),
]
ARTIFACT_FILES = [
    "requirement.ir.json",
    "bindings.json",
    "assumptions.json",
    "review.json",
    "verification-tasks.json",
    "adapter-results.json",
    "generated-tests.json",
    "counterexamples.json",
    "normalized-traces.json",
    "evidence.json",
    "status.json",
    "implementation-spec.md",
    "smt/C1.smt2",
]


def build_package_index(
    packages_dir: Path, *, python_adapter: PythonPackageAdapter | None = None
) -> dict[str, Any]:
    package_dirs = find_package_dirs(packages_dir)
    if not package_dirs:
        raise ValueError(f"no package directories found under {packages_dir}")
    packages = [_summarize_package(path, python_adapter=python_adapter) for path in package_dirs]
    return {
        "index_version": INDEX_VERSION,
        "packages_root": _path(packages_dir),
        "summary": _index_summary(packages),
        "packages": packages,
    }


def build_ci_report(
    packages_dir: Path, *, python_adapter: PythonPackageAdapter | None = None
) -> dict[str, Any]:
    package_index = build_package_index(packages_dir, python_adapter=python_adapter)
    findings = _ci_findings(package_index["packages"])
    return {
        "report_version": REPORT_VERSION,
        "mode": "shadow",
        "result": "report_only",
        "summary": {
            **package_index["summary"],
            "findings": len(findings),
            "error_findings": sum(1 for finding in findings if finding["severity"] == "error"),
            "warning_findings": sum(1 for finding in findings if finding["severity"] == "warning"),
        },
        "findings": findings,
        "package_index": package_index,
    }


def build_soft_gate_report(
    packages_dir: Path,
    *,
    requirement_ids: list[str],
    python_adapter: PythonPackageAdapter | None = None,
) -> dict[str, Any]:
    package_index = build_package_index(packages_dir, python_adapter=python_adapter)
    referenced_ids = _stable_unique(requirement_ids)
    packages_by_id = {
        package["requirement_id"]: package
        for package in package_index["packages"]
        if package["requirement_id"]
    }
    findings = _soft_gate_findings(referenced_ids, packages_by_id)
    blocking_findings = [finding for finding in findings if finding["severity"] == "blocker"]
    warning_findings = [finding for finding in findings if finding["severity"] == "warning"]
    return {
        "report_version": REPORT_VERSION,
        "mode": "soft_gate",
        "result": "blocked" if blocking_findings else "pass",
        "references": referenced_ids,
        "summary": {
            **package_index["summary"],
            "referenced": len(referenced_ids),
            "missing_references": sum(
                1 for finding in findings if finding["category"] == "missing_requirement_reference"
            ),
            "unknown_references": sum(
                1 for finding in findings if finding["category"] == "unknown_requirement_reference"
            ),
            "blocking_findings": len(blocking_findings),
            "warning_findings": len(warning_findings),
            "findings": len(findings),
        },
        "findings": findings,
        "referenced_packages": [
            packages_by_id[requirement_id]
            for requirement_id in referenced_ids
            if requirement_id in packages_by_id
        ],
        "package_index": package_index,
    }


def extract_requirement_ids(text: str) -> list[str]:
    return _stable_unique(REQUIREMENT_ID_PATTERN.findall(text))


def ci_report_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    mode = report["mode"]
    title = "NLReq Soft Gate Report" if mode == "soft_gate" else "NLReq CI Shadow Report"
    lines = [
        f"# {title}",
        "",
        f"Mode: `{mode}`",
        f"Result: `{report['result']}`",
        "",
        "## Summary",
        "",
        f"- Packages: {summary['total']}",
        f"- Valid packages: {summary['valid']}",
        f"- Invalid packages: {summary['invalid']}",
        f"- Accepted packages: {summary['accepted']}",
        f"- Refused packages: {summary['refused']}",
        f"- Findings: {summary['findings']}",
        "",
    ]
    if mode == "soft_gate":
        lines.extend(
            [
                f"- Referenced requirements: {summary['referenced']}",
                f"- Blocking findings: {summary['blocking_findings']}",
                "",
                "## References",
                "",
            ]
        )
        references = report.get("references", [])
        if references:
            lines.append(", ".join(f"`{requirement_id}`" for requirement_id in references))
        else:
            lines.append("No requirement references found.")
        lines.append("")
    lines.extend(["## Findings", ""])
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
                    requirement_id=finding["requirement_id"] or "-",
                    message=_escape_markdown_table(finding["message"]),
                )
            )
    return "\n".join(lines) + "\n"


def review_checklist_template(requirement_id: str | None = None) -> str:
    title = "# Requirement Review Checklist"
    lines = [title, ""]
    if requirement_id:
        lines.extend([f"Requirement: `{requirement_id}`", ""])
    lines.extend(
        [
            "## Checklist",
            "",
            *[f"- [ ] {label}" for _field, label in REVIEW_CHECKLIST_ITEMS],
            "",
            "## Decision",
            "",
            "- [ ] approved",
            "- [ ] needs_review",
            "- [ ] rejected",
            "",
            "## Reviewer",
            "",
            "- Reviewer:",
            "- Timestamp:",
            "- Self-audit: yes / no",
            "- Follow-up items:",
        ]
    )
    return "\n".join(lines) + "\n"


def find_package_dirs(root: Path) -> list[Path]:
    if not root.exists():
        return []
    return sorted(path for path in root.iterdir() if (path / "requirement.ir.json").is_file())


def _summarize_package(
    package_dir: Path, *, python_adapter: PythonPackageAdapter | None
) -> dict[str, Any]:
    validation_status = "valid"
    validation_errors: list[str] = []
    validation_kind = "python_package" if (package_dir / "adapter-results.json").is_file() else "generic"
    if validation_kind == "python_package" and python_adapter is None:
        validation_status = "skipped"
        validation_errors.append("python adapter validation requires --python-package-root")
        ir = _read_model(package_dir / "requirement.ir.json", RequirementIR)
        evidence = _read_model(package_dir / "evidence.json", EvidenceObject)
        status = _read_model(package_dir / "status.json", StatusDecision)
    else:
        try:
            if validation_kind == "python_package":
                ir, evidence, status = validate_python_package(package_dir, python_adapter)
            else:
                ir, evidence, status = validate_package(package_dir)
        except (OSError, ValidationError, ValueError) as exc:
            validation_status = "invalid"
            validation_errors.append(str(exc))
            ir = _read_model(package_dir / "requirement.ir.json", RequirementIR)
            evidence = _read_model(package_dir / "evidence.json", EvidenceObject)
            status = _read_model(package_dir / "status.json", StatusDecision)

    review = _read_model(package_dir / "review.json", ReviewArtifact)
    return {
        "path": _path(package_dir),
        "requirement_id": ir.requirement_id if ir else None,
        "title": ir.title if ir else None,
        "claim_kind": ir.claim.kind if ir else None,
        "adapter": _adapter_id(ir, validation_kind),
        "validation_kind": validation_kind,
        "validation_status": validation_status,
        "validation_errors": validation_errors,
        "status": status.status.value if status else None,
        "status_reason": status.reason if status else None,
        "review": _review_summary(review),
        "evidence": _evidence_summary(evidence),
        "artifacts": _artifact_hashes(package_dir),
    }


def _read_model(path: Path, model: type[Any]) -> Any | None:
    try:
        return model.model_validate_json(path.read_text())
    except (OSError, ValidationError, ValueError):
        return None


def _adapter_id(ir: RequirementIR | None, validation_kind: str) -> str:
    if not ir:
        return validation_kind
    adapter_ids = sorted({binding.adapter for binding in ir.bindings.values()})
    if len(adapter_ids) == 1:
        return adapter_ids[0]
    if adapter_ids:
        return "mixed"
    return validation_kind


def _review_summary(review: ReviewArtifact | None) -> dict[str, Any]:
    if review is None:
        return {
            "decision": None,
            "reviewer": None,
            "self_audit": None,
            "timestamp": None,
            "checklist": {},
        }
    return {
        "decision": review.decision,
        "reviewer": review.reviewer,
        "self_audit": review.self_audit,
        "timestamp": review.timestamp,
        "checklist": review.checklist.model_dump(mode="json"),
    }


def _evidence_summary(evidence: EvidenceObject | None) -> dict[str, Any]:
    if evidence is None:
        return {
            "ir_hash": None,
            "claims": [],
            "unbound_symbols": [],
            "ambiguous_symbols": [],
            "unsupported_claims": [],
            "failed_checks": [],
            "timeouts": [],
            "pending_reviews": [],
            "needs_spec_coverage": False,
        }
    return {
        "ir_hash": evidence.ir_hash,
        "claims": [
            {
                "id": claim.id,
                "required_evidence": claim.required_evidence.value,
                "achieved_evidence": claim.achieved_evidence.value if claim.achieved_evidence else None,
            }
            for claim in evidence.claims
        ],
        "unbound_symbols": evidence.unbound_symbols,
        "ambiguous_symbols": evidence.ambiguous_symbols,
        "unsupported_claims": evidence.unsupported_claims,
        "failed_checks": evidence.failed_checks,
        "timeouts": evidence.timeouts,
        "pending_reviews": evidence.pending_reviews,
        "needs_spec_coverage": evidence.needs_spec_coverage,
    }


def _artifact_hashes(package_dir: Path) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for artifact in ARTIFACT_FILES:
        path = package_dir / artifact
        if path.is_file():
            hashes[artifact] = sha256_text(path.read_text())
    return hashes


def _index_summary(packages: list[dict[str, Any]]) -> dict[str, int]:
    statuses = [package["status"] for package in packages if package["status"]]
    return {
        "total": len(packages),
        "valid": sum(1 for package in packages if package["validation_status"] == "valid"),
        "invalid": sum(1 for package in packages if package["validation_status"] == "invalid"),
        "validation_skipped": sum(
            1 for package in packages if package["validation_status"] == "skipped"
        ),
        "accepted": sum(1 for status in statuses if status.startswith("ACCEPTED")),
        "refused": sum(1 for status in statuses if status.startswith("REFUSED")),
        "needs_spec_coverage": sum(
            1 for package in packages if package["evidence"]["needs_spec_coverage"]
        ),
        "unresolved_bindings": sum(
            1 for package in packages if package["evidence"]["unbound_symbols"]
        ),
        "ambiguous_bindings": sum(
            1 for package in packages if package["evidence"]["ambiguous_symbols"]
        ),
        "failed_checks": sum(1 for package in packages if package["evidence"]["failed_checks"]),
        "unsupported_claims": sum(
            1 for package in packages if package["evidence"]["unsupported_claims"]
        ),
        "pending_reviews": sum(
            1
            for package in packages
            if package["evidence"]["pending_reviews"] or package["review"]["decision"] != "approved"
        ),
    }


def _ci_findings(packages: list[dict[str, Any]]) -> list[dict[str, str | None]]:
    findings: list[dict[str, str | None]] = []
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
        if evidence["unbound_symbols"]:
            findings.append(
                _finding(
                    "warning",
                    "unresolved_bindings",
                    requirement_id,
                    path,
                    "unbound symbols: " + ", ".join(evidence["unbound_symbols"]),
                )
            )
        if evidence["ambiguous_symbols"]:
            findings.append(
                _finding(
                    "warning",
                    "unresolved_bindings",
                    requirement_id,
                    path,
                    "ambiguous symbols: " + ", ".join(evidence["ambiguous_symbols"]),
                )
            )
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
        if evidence["pending_reviews"]:
            findings.append(
                _finding(
                    "warning",
                    "pending_reviews",
                    requirement_id,
                    path,
                    "pending reviews: " + ", ".join(evidence["pending_reviews"]),
                )
            )
        if package["review"]["decision"] != "approved":
            findings.append(
                _finding(
                    "warning",
                    "pending_reviews",
                    requirement_id,
                    path,
                    "review decision is not approved",
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


def _soft_gate_findings(
    referenced_ids: list[str], packages_by_id: dict[str, dict[str, Any]]
) -> list[dict[str, str | None]]:
    if not referenced_ids:
        return [
            _finding(
                "blocker",
                "missing_requirement_reference",
                None,
                "",
                "implementation change does not reference a requirement package",
            )
        ]

    findings: list[dict[str, str | None]] = []
    for requirement_id in referenced_ids:
        package = packages_by_id.get(requirement_id)
        if package is None:
            findings.append(
                _finding(
                    "blocker",
                    "unknown_requirement_reference",
                    requirement_id,
                    "",
                    "referenced requirement package was not found",
                )
            )
            continue

        path = package["path"]
        validation_status = package["validation_status"]
        if validation_status != "valid":
            message = "; ".join(package["validation_errors"]) or (
                f"package validation status is {validation_status}"
            )
            findings.append(
                _finding("blocker", _validation_category(message), requirement_id, path, message)
            )

        status = package["status"]
        if status is None:
            findings.append(
                _finding(
                    "blocker",
                    "status",
                    requirement_id,
                    path,
                    "referenced package has no status",
                )
            )
        elif not str(status).startswith("ACCEPTED"):
            findings.append(
                _finding(
                    "blocker",
                    "status",
                    requirement_id,
                    path,
                    f"referenced package status is {status}",
                )
            )

        review = package["review"]
        if review["decision"] != "approved":
            findings.append(
                _finding(
                    "blocker",
                    "pending_reviews",
                    requirement_id,
                    path,
                    "referenced package review decision is not approved",
                )
            )

        evidence = package["evidence"]
        if evidence["pending_reviews"]:
            findings.append(
                _finding(
                    "blocker",
                    "pending_reviews",
                    requirement_id,
                    path,
                    "pending reviews: " + ", ".join(evidence["pending_reviews"]),
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
    return findings


def _finding(
    severity: str,
    category: str,
    requirement_id: str | None,
    path: str,
    message: str,
) -> dict[str, str | None]:
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


def _path(path: Path) -> str:
    return path.as_posix()


def _escape_markdown_table(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def _stable_unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        if value not in seen:
            unique.append(value)
            seen.add(value)
    return unique
