from __future__ import annotations

from fnmatch import fnmatchcase
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .adoption import find_package_dirs
from .jsonutil import read_json, sha256_text
from .models import EvidenceLevel, RequirementIR


ROUTING_VERSION = "0.1"
ROUTE_DECISIONS = {
    "selected",
    "report_only",
    "missing_adapter",
    "unsupported_claim",
    "ambiguous_route",
    "out_of_scope",
}


class AdapterConformanceSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["pass", "fail", "unknown"] = "unknown"
    suite_version: str | None = None


class RegisteredAdapter(BaseModel):
    model_config = ConfigDict(extra="forbid")

    adapter_id: str
    target_kind: str
    supported_claim_kinds: list[str] = Field(default_factory=list)
    supported_evidence: list[EvidenceLevel] = Field(default_factory=list)
    conformance: AdapterConformanceSummary = Field(default_factory=AdapterConformanceSummary)
    gateable: bool = False
    rollout: Literal["stable", "report_only", "experimental"] = "stable"


class AdapterRegistryArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    registry_version: Literal["0.1"] = ROUTING_VERSION
    adapters: list[RegisteredAdapter] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_unique_adapter_ids(self) -> AdapterRegistryArtifact:
        adapter_ids = [adapter.adapter_id for adapter in self.adapters]
        if len(adapter_ids) != len(set(adapter_ids)):
            raise ValueError("adapter ids must be unique")
        return self


class RoutingRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    path_patterns: list[str] = Field(default_factory=list)
    requirement_id_patterns: list[str] = Field(default_factory=list)
    target_kind: str | None = None
    adapter: str | None = None
    minimum_evidence: list[EvidenceLevel] = Field(default_factory=list)
    report_only: bool = False


class RoutingPolicyArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    routing_version: Literal["0.1"] = ROUTING_VERSION
    rules: list[RoutingRule] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_unique_rule_names(self) -> RoutingPolicyArtifact:
        names = [rule.name for rule in self.rules]
        if len(names) != len(set(names)):
            raise ValueError("routing rule names must be unique")
        return self


def load_adapter_registry(path: Path) -> AdapterRegistryArtifact:
    return AdapterRegistryArtifact.model_validate(read_json(path))


def load_routing_policy(path: Path) -> RoutingPolicyArtifact:
    return RoutingPolicyArtifact.model_validate(read_json(path))


def build_routing_report(
    packages_dir: Path,
    *,
    registry: AdapterRegistryArtifact,
    policy: RoutingPolicyArtifact,
    changed_paths: list[str] | None = None,
    requirement_ids: list[str] | None = None,
    registry_path: Path | None = None,
    policy_path: Path | None = None,
) -> dict[str, Any]:
    changed_paths = [_normalize_path(path) for path in changed_paths or []]
    wanted = set(requirement_ids or [])
    adapters_by_id = {adapter.adapter_id: adapter for adapter in registry.adapters}
    routes: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []
    for package_dir in find_package_dirs(packages_dir):
        ir = RequirementIR.model_validate_json((package_dir / "requirement.ir.json").read_text())
        if wanted and ir.requirement_id not in wanted:
            continue
        package_routes = _routes_for_package(
            ir,
            package_dir=package_dir,
            adapters_by_id=adapters_by_id,
            policy=policy,
            changed_paths=changed_paths,
        )
        routes.extend(package_routes)
        findings.extend(_findings_for_routes(package_routes))

    summary = {decision: sum(1 for route in routes if route["decision"] == decision) for decision in ROUTE_DECISIONS}
    return {
        "report_version": ROUTING_VERSION,
        "mode": "adapter_routing",
        "result": "report_only",
        "inputs": {
            "packages_root": packages_dir.as_posix(),
            "adapter_registry_hash": _file_hash(registry_path),
            "routing_policy_hash": _file_hash(policy_path),
            "changed_paths": changed_paths,
        },
        "summary": {
            "packages": len({route["requirement_id"] for route in routes}),
            **{key: summary[key] for key in sorted(summary)},
            "findings": len(findings),
        },
        "routes": routes,
        "findings": findings,
    }


def routing_report_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# NLReq Adapter Routing Report",
        "",
        f"Result: `{report['result']}`",
        "",
        "## Summary",
        "",
        f"- Packages: {summary['packages']}",
        f"- Selected: {summary['selected']}",
        f"- Report-only: {summary['report_only']}",
        f"- Missing adapters: {summary['missing_adapter']}",
        f"- Ambiguous routes: {summary['ambiguous_route']}",
        f"- Unsupported claims: {summary['unsupported_claim']}",
        f"- Out of scope: {summary['out_of_scope']}",
        f"- Findings: {summary['findings']}",
        "",
        "## Routes",
        "",
    ]
    if not report["routes"]:
        lines.append("No routes.")
    else:
        lines.extend(
            [
                "| Decision | Requirement | Adapter | Target | Evidence | Reason |",
                "|---|---|---|---|---|---|",
            ]
        )
        for route in report["routes"]:
            lines.append(
                "| {decision} | {requirement_id} | {adapter} | {target_kind} | {evidence} | {reason} |".format(
                    decision=route["decision"],
                    requirement_id=route["requirement_id"],
                    adapter=route.get("adapter") or "-",
                    target_kind=route.get("target_kind") or "-",
                    evidence=", ".join(route.get("minimum_evidence", [])) or "-",
                    reason=_escape_markdown_table(route["reason"]),
                )
            )
    if report["findings"]:
        lines.extend(["", "## Findings", ""])
        lines.extend(
            [
                "| Severity | Category | Requirement | Message |",
                "|---|---|---|---|---|",
            ]
        )
        for finding in report["findings"]:
            lines.append(
                "| {severity} | {category} | {requirement_id} | {message} |".format(
                    severity=finding["severity"],
                    category=finding["category"],
                    requirement_id=finding.get("requirement_id") or "-",
                    message=_escape_markdown_table(finding["message"]),
                )
            )
    return "\n".join(lines) + "\n"


def _routes_for_package(
    ir: RequirementIR,
    *,
    package_dir: Path,
    adapters_by_id: dict[str, RegisteredAdapter],
    policy: RoutingPolicyArtifact,
    changed_paths: list[str],
) -> list[dict[str, Any]]:
    matching_rules = [
        rule for rule in policy.rules if _rule_matches(rule, ir, changed_paths)
    ]
    if not matching_rules:
        return [
            _route(
                ir,
                package_dir=package_dir,
                rule=None,
                adapter=None,
                decision="out_of_scope",
                reason="no routing policy rule matched the requirement and changed paths",
            )
        ]

    routes: list[dict[str, Any]] = []
    for rule in matching_rules:
        if rule.adapter:
            adapter = adapters_by_id.get(rule.adapter)
            if adapter is None:
                routes.append(
                    _route(
                        ir,
                        package_dir=package_dir,
                        rule=rule,
                        adapter=None,
                        decision="missing_adapter",
                        reason=f"routing rule {rule.name} selected unavailable adapter {rule.adapter}",
                    )
                )
                continue
            routes.append(_route_for_adapter(ir, package_dir=package_dir, rule=rule, adapter=adapter))
            continue

        candidates = _candidate_adapters(ir, adapters_by_id.values(), rule)
        if not candidates:
            routes.append(
                _route(
                    ir,
                    package_dir=package_dir,
                    rule=rule,
                    adapter=None,
                    decision="unsupported_claim",
                    reason=f"no registered adapter supports rule {rule.name} for claim {ir.claim.kind}",
                )
            )
        elif len(candidates) > 1:
            routes.append(
                _route(
                    ir,
                    package_dir=package_dir,
                    rule=rule,
                    adapter=None,
                    decision="ambiguous_route",
                    reason="multiple adapters match: "
                    + ", ".join(adapter.adapter_id for adapter in candidates),
                )
            )
        else:
            routes.append(
                _route_for_adapter(
                    ir,
                    package_dir=package_dir,
                    rule=rule,
                    adapter=candidates[0],
                )
            )
    return routes


def _route_for_adapter(
    ir: RequirementIR,
    *,
    package_dir: Path,
    rule: RoutingRule,
    adapter: RegisteredAdapter,
) -> dict[str, Any]:
    unsupported = _unsupported_reason(ir, rule, adapter)
    if unsupported:
        return _route(
            ir,
            package_dir=package_dir,
            rule=rule,
            adapter=adapter,
            decision="unsupported_claim",
            reason=unsupported,
        )
    report_only = (
        rule.report_only
        or not adapter.gateable
        or adapter.rollout != "stable"
        or adapter.conformance.status != "pass"
    )
    return _route(
        ir,
        package_dir=package_dir,
        rule=rule,
        adapter=adapter,
        decision="report_only" if report_only else "selected",
        reason=_selection_reason(rule, adapter, report_only),
    )


def _candidate_adapters(
    ir: RequirementIR,
    adapters: list[RegisteredAdapter] | Any,
    rule: RoutingRule,
) -> list[RegisteredAdapter]:
    candidates = []
    for adapter in adapters:
        if rule.target_kind and adapter.target_kind != rule.target_kind:
            continue
        if _unsupported_reason(ir, rule, adapter):
            continue
        candidates.append(adapter)
    return sorted(candidates, key=lambda adapter: adapter.adapter_id)


def _unsupported_reason(
    ir: RequirementIR,
    rule: RoutingRule,
    adapter: RegisteredAdapter,
) -> str | None:
    if rule.target_kind and adapter.target_kind != rule.target_kind:
        return (
            f"adapter {adapter.adapter_id} target kind {adapter.target_kind} "
            f"does not match required {rule.target_kind}"
        )
    if ir.claim.kind not in adapter.supported_claim_kinds:
        return f"adapter {adapter.adapter_id} does not support claim kind {ir.claim.kind}"
    missing_evidence = [
        level.value
        for level in rule.minimum_evidence
        if level not in adapter.supported_evidence
    ]
    if missing_evidence:
        return (
            f"adapter {adapter.adapter_id} does not support required evidence "
            + ", ".join(missing_evidence)
        )
    return None


def _rule_matches(rule: RoutingRule, ir: RequirementIR, changed_paths: list[str]) -> bool:
    if rule.requirement_id_patterns and not _matches_any(
        ir.requirement_id, rule.requirement_id_patterns
    ):
        return False
    if rule.path_patterns:
        if not changed_paths:
            return False
        if not any(_matches_any(path, rule.path_patterns) for path in changed_paths):
            return False
    return True


def _route(
    ir: RequirementIR,
    *,
    package_dir: Path,
    rule: RoutingRule | None,
    adapter: RegisteredAdapter | None,
    decision: str,
    reason: str,
) -> dict[str, Any]:
    return {
        "requirement_id": ir.requirement_id,
        "package_path": package_dir.as_posix(),
        "claim_kind": ir.claim.kind,
        "target_kind": adapter.target_kind if adapter else rule.target_kind if rule else None,
        "adapter": adapter.adapter_id if adapter else rule.adapter if rule else None,
        "rule": rule.name if rule else None,
        "decision": decision,
        "reason": reason,
        "minimum_evidence": [
            level.value for level in rule.minimum_evidence
        ]
        if rule
        else [],
        "gateable": bool(adapter.gateable) if adapter else False,
    }


def _selection_reason(
    rule: RoutingRule,
    adapter: RegisteredAdapter,
    report_only: bool,
) -> str:
    if report_only:
        if rule.report_only:
            return f"routing rule {rule.name} selected {adapter.adapter_id} in report-only mode"
        if adapter.conformance.status != "pass":
            return f"adapter {adapter.adapter_id} conformance status is {adapter.conformance.status}"
        if not adapter.gateable:
            return f"adapter {adapter.adapter_id} is not gateable"
        return f"adapter {adapter.adapter_id} rollout is {adapter.rollout}"
    return f"routing rule {rule.name} selected {adapter.adapter_id}"


def _findings_for_routes(routes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    findings = []
    for route in routes:
        if route["decision"] in {"selected", "report_only", "out_of_scope"}:
            continue
        findings.append(
            {
                "severity": "warning",
                "category": route["decision"],
                "requirement_id": route["requirement_id"],
                "path": route["package_path"],
                "message": route["reason"],
            }
        )
    return findings


def _file_hash(path: Path | None) -> str | None:
    if path is None or not path.is_file():
        return None
    return sha256_text(path.read_text())


def _matches_any(value: str, patterns: list[str]) -> bool:
    normalized = _normalize_path(value)
    for pattern in patterns:
        normalized_pattern = _normalize_path(pattern)
        if fnmatchcase(normalized, normalized_pattern):
            return True
        if "/**/" in normalized_pattern and fnmatchcase(
            normalized, normalized_pattern.replace("/**/", "/")
        ):
            return True
    return False


def _normalize_path(path: str | Path) -> str:
    return Path(path).as_posix()


def _escape_markdown_table(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")
