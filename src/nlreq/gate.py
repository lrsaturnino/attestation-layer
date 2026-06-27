from __future__ import annotations

from datetime import datetime, timedelta, timezone
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .adoption import build_package_index
from .asyncapi_adapter import AsyncApiAdapter
from .command_adapter import CommandAdapter
from .graphql_adapter import GraphQlAdapter
from .jsonschema_adapter import JsonSchemaAdapter
from .jsonutil import read_json
from .models import EvidenceLevel, FinalStatus
from .openapi_adapter import OpenApiAdapter
from .protobuf_adapter import ProtobufAdapter
from .python_adapter import PythonPackageAdapter
from .tla_adapter import TlaAdapter


HARD_GATE_REPORT_VERSION = "0.1"
COMMON_BLOCKING_FINDINGS = [
    "missing_requirement_reference",
    "unknown_requirement_reference",
    "package_validity",
    "stale_evidence",
    "status",
    "pending_reviews",
]
ARTIFACT_HASH_ALIASES = {
    "requirement_ir": "requirement.ir.json",
    "requirement.ir": "requirement.ir.json",
    "status": "status.json",
    "evidence": "evidence.json",
    "review": "review.json",
    "bindings": "bindings.json",
    "assumptions": "assumptions.json",
    "verification_tasks": "verification-tasks.json",
    "verification-tasks": "verification-tasks.json",
    "implementation_spec": "implementation-spec.md",
    "implementation-spec": "implementation-spec.md",
}


class GatePolicyScope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    adapters: list[str] = Field(default_factory=list)
    changed_path_patterns: list[str] = Field(default_factory=list)
    package_roots: list[str] = Field(default_factory=list)
    requirement_id_patterns: list[str] = Field(default_factory=list)


class GateMachinePinRules(BaseModel):
    """The DEFAULT-DENY machine-pin gate (three-zone scope §6; acceptance #4).

    A machine-pinned status (``MACHINE_PINNED_PENDING_REVIEW``) is accepted by the hard gate ONLY
    for a change whose EVERY changed path matches an explicit low-risk allow-list pattern AND
    whose NO changed path matches a block-list pattern (auth / funds / other sensitive surfaces).
    This is default-deny: an UNMATCHED path (one not on the allow-list), a MIXED-risk change (some
    allowed + some not), and EVERY auth/funds path all require a human ``REVIEWED`` package — a
    machine pin never satisfies them (scope §6 / AC4). Evidence-level requirements are unchanged:
    machine pinning never substitutes for a deterministic proof level (the ``minimum_evidence``
    check still runs on a machine-pinned package).

    ``enabled=False`` (the default) means the gate blocks a machine-pinned status on EVERY path
    — the operator opts into per-path acceptance by enabling the section and populating the
    allow-list. An empty allow-list with ``enabled=True`` is default-deny against every path
    (nothing is allow-listed), which is the safe floor.
    """

    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    # fnmatch patterns for low-risk changed paths a machine pin MAY satisfy (e.g. 'docs/**',
    # 'tests/**'). A machine-pinned package is accepted iff EVERY changed path matches at least
    # one pattern here AND none match ``block_changed_path_patterns``.
    allowed_changed_path_patterns: list[str] = Field(default_factory=list)
    # fnmatch patterns for sensitive paths a machine pin MUST NEVER satisfy, even if they also
    # match the allow-list (deny wins). Defaults to auth/funds surfaces; an operator widens it.
    block_changed_path_patterns: list[str] = Field(
        default_factory=lambda: [
            "**/auth/**",
            "**/authentication/**",
            "**/authz/**",
            "**/funds/**",
            "**/payments/**",
            "**/wallet/**",
            "**/transfer/**",
            "**/signing/**",
            "**/crypto/**",
        ]
    )


class GatePolicyRules(BaseModel):
    """The enforceable rules of a hard-gate policy.

    SCHEMA BOUNDARY (ADR 0206 §5): the committed ``schemas/gate-policy.schema.json`` is an
    AUTO-GENERATED structural contract (``scripts/generate_schema.py`` from the Pydantic models,
    enforced drift-free by ``scripts/check_schema_drift.py``). It is NOT the authoring contract:
    Pydantic validation (``load_gate_policy`` -> ``GatePolicy.model_validate``) is authoritative,
    and semantic / cross-field constraints that the JSON Schema cannot express live in the
    ``model_validator`` below. In particular ``allowed_statuses`` is typed ``list[FinalStatus]``
    so the generated enum advertises every ``FinalStatus`` member (including
    ``MACHINE_PINNED_PENDING_REVIEW``), but the runtime validator REFUSES that member in
    ``allowed_statuses``: a machine pin is accepted ONLY per-path via the dedicated
    ``GatePolicy.machine_pin`` default-deny section (allow-list), never globally via
    ``allowed_statuses`` — so a hand-authored
    policy that lists it fails LOUDLY at load time (never silently accepted). The same boundary
    applies to ``PinningProvenance``
    backing guards (the schema requires only ``kind`` + ``timestamp``; the ``ensemble`` /
    real-review-event backing is enforced at runtime).
    """

    model_config = ConfigDict(extra="forbid")

    allowed_statuses: list[FinalStatus] = Field(
        default_factory=lambda: [FinalStatus.ACCEPTED_WITH_EVIDENCE]
    )
    block_findings: list[str] = Field(default_factory=lambda: list(COMMON_BLOCKING_FINDINGS))
    minimum_evidence: list[EvidenceLevel] = Field(default_factory=list)
    require_approved_review: bool = True
    report_only_findings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _reject_machine_pinned_status_in_allowed_statuses(self) -> GatePolicyRules:
        # A machine-pinned status (``MACHINE_PINNED_PENDING_REVIEW``) is accepted ONLY per-path via
        # the dedicated ``GatePolicy.machine_pin`` default-deny section (scope §6 / AC4), NEVER
        # globally via ``allowed_statuses`` — so a hand-authored policy that lists it fails LOUDLY
        # at load time. ``allowed_statuses`` is for the human-accepted statuses
        # (``ACCEPTED_WITH_EVIDENCE`` / ``ACCEPTED_FOR_IMPLEMENTATION_WITH_REVIEW``); the machine
        # pin has its own per-path gate precisely so an operator cannot blanket-allow it.
        if any(status is FinalStatus.MACHINE_PINNED_PENDING_REVIEW for status in self.allowed_statuses):
            raise ValueError(
                "MACHINE_PINNED_PENDING_REVIEW is not allowed in rules.allowed_statuses: a "
                "machine-pinned status is accepted ONLY per-path via the policy's machine_pin "
                "default-deny section (allowed_changed_path_patterns), never globally"
            )
        return self


class GatePolicyWaiverRules(BaseModel):
    model_config = ConfigDict(extra="forbid")

    allow_waivers: bool = False
    max_duration_days: int | None = Field(default=None, gt=0)
    require_reviewed_hashes: bool = True


class GatePolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    policy_id: str
    schema_version: str = "0.1"
    mode: Literal["hard_gate"] = "hard_gate"
    scope: GatePolicyScope = Field(default_factory=GatePolicyScope)
    rules: GatePolicyRules = Field(default_factory=GatePolicyRules)
    waivers: GatePolicyWaiverRules = Field(default_factory=GatePolicyWaiverRules)
    # The default-deny machine-pin gate (scope §6 / AC4). Defaults to disabled (default-deny on
    # every path): a machine-pinned status is blocked on every path until an operator enables the
    # section and populates the low-risk allow-list.
    machine_pin: GateMachinePinRules = Field(default_factory=GateMachinePinRules)

    @model_validator(mode="after")
    def validate_schema_version(self) -> GatePolicy:
        if self.schema_version != "0.1":
            raise ValueError(f"unsupported gate policy schema_version: {self.schema_version}")
        return self


class GateWaiver(BaseModel):
    model_config = ConfigDict(extra="forbid")

    waiver_id: str
    schema_version: str = "0.1"
    requirement_ids: list[str] = Field(default_factory=list)
    package_paths: list[str] = Field(default_factory=list)
    reviewer: str
    reason: str
    expires_at: datetime
    reviewed_hashes: dict[str, str] = Field(default_factory=dict)
    linked_issue: str
    may_satisfy_hard_gate: bool = True

    @model_validator(mode="after")
    def validate_waiver(self) -> GateWaiver:
        if self.schema_version != "0.1":
            raise ValueError(f"unsupported waiver schema_version: {self.schema_version}")
        if not self.requirement_ids and not self.package_paths:
            raise ValueError("waiver must cover at least one requirement id or package path")
        if self.expires_at.tzinfo is None:
            raise ValueError("expires_at must include a timezone")
        return self


def load_gate_policy(path: Path) -> GatePolicy:
    return GatePolicy.model_validate(read_json(path))


def load_gate_waivers(paths: list[Path]) -> list[GateWaiver]:
    waivers: list[GateWaiver] = []
    for path in paths:
        value = read_json(path)
        if isinstance(value, list):
            waivers.extend(GateWaiver.model_validate(item) for item in value)
        else:
            waivers.append(GateWaiver.model_validate(value))
    return waivers


def build_hard_gate_report(
    packages_dir: Path,
    *,
    requirement_ids: list[str],
    policy: GatePolicy,
    waivers: list[GateWaiver] | None = None,
    changed_paths: list[str] | None = None,
    python_adapter: PythonPackageAdapter | None = None,
    openapi_adapter: OpenApiAdapter | None = None,
    command_adapter: CommandAdapter | None = None,
    tla_adapter: TlaAdapter | None = None,
    graphql_adapter: GraphQlAdapter | None = None,
    json_schema_adapter: JsonSchemaAdapter | None = None,
    asyncapi_adapter: AsyncApiAdapter | None = None,
    protobuf_adapter: ProtobufAdapter | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
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
    referenced_ids = _stable_unique(requirement_ids)
    packages_by_id = {
        package["requirement_id"]: package
        for package in package_index["packages"]
        if package["requirement_id"]
    }
    normalized_changed_paths = [_normalize_path(path) for path in changed_paths or []]
    raw_findings = _raw_hard_gate_findings(
        referenced_ids, packages_by_id, policy, changed_paths=normalized_changed_paths
    )
    evaluated_findings: list[dict[str, Any]] = []
    waiver_decisions: list[dict[str, Any]] = []
    active_now = _as_utc(now or datetime.now(timezone.utc))
    active_waivers = waivers or []

    for finding in raw_findings:
        package = packages_by_id.get(finding["requirement_id"])
        evaluated, decisions = _evaluate_finding(
            finding,
            package=package,
            packages_dir=packages_dir,
            policy=policy,
            waivers=active_waivers,
            changed_paths=normalized_changed_paths,
            now=active_now,
        )
        evaluated_findings.append(evaluated)
        waiver_decisions.extend(decisions)

    hard_blocking = [
        finding for finding in evaluated_findings if finding["enforcement"] == "blocking"
    ]
    waived = [finding for finding in evaluated_findings if finding["enforcement"] == "waived"]
    report_only = [
        finding
        for finding in evaluated_findings
        if finding["enforcement"] in {"report_only", "out_of_scope"}
    ]
    out_of_scope = [
        finding for finding in evaluated_findings if finding["enforcement"] == "out_of_scope"
    ]
    return {
        "report_version": HARD_GATE_REPORT_VERSION,
        "mode": "hard_gate",
        "result": "blocked" if hard_blocking else "pass",
        "policy": {
            "policy_id": policy.policy_id,
            "schema_version": policy.schema_version,
        },
        "scope": {
            "changed_paths": normalized_changed_paths,
        },
        "references": referenced_ids,
        "summary": {
            **package_index["summary"],
            "referenced": len(referenced_ids),
            "hard_blocking_findings": len(hard_blocking),
            "waived_findings": len(waived),
            "report_only_findings": len(report_only),
            "out_of_scope_findings": len(out_of_scope),
            "findings": len(evaluated_findings),
            "waiver_decisions": len(waiver_decisions),
        },
        "findings": evaluated_findings,
        "waiver_decisions": waiver_decisions,
        "referenced_packages": [
            packages_by_id[requirement_id]
            for requirement_id in referenced_ids
            if requirement_id in packages_by_id
        ],
        "package_index": package_index,
    }


def hard_gate_report_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# NLReq Hard Gate Report",
        "",
        f"Mode: `{report['mode']}`",
        f"Result: `{report['result']}`",
        f"Policy: `{report['policy']['policy_id']}`",
        "",
        "## Summary",
        "",
        f"- Packages: {summary['total']}",
        f"- Referenced requirements: {summary['referenced']}",
        f"- Hard blocking findings: {summary['hard_blocking_findings']}",
        f"- Waived findings: {summary['waived_findings']}",
        f"- Report-only findings: {summary['report_only_findings']}",
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
                "| Enforcement | Category | Requirement | Waiver | Message |",
                "|---|---|---|---|---|",
            ]
        )
        for finding in findings:
            lines.append(
                "| {enforcement} | {category} | {requirement_id} | {waiver_id} | {message} |".format(
                    enforcement=finding["enforcement"],
                    category=finding["category"],
                    requirement_id=finding["requirement_id"] or "-",
                    waiver_id=finding.get("waiver_id") or "-",
                    message=_escape_markdown_table(finding["message"]),
                )
            )
    if report["waiver_decisions"]:
        lines.extend(["", "## Waivers", ""])
        lines.extend(
            [
                "| Decision | Waiver | Requirement | Category | Reason |",
                "|---|---|---|---|---|",
            ]
        )
        for decision in report["waiver_decisions"]:
            lines.append(
                "| {decision} | {waiver_id} | {requirement_id} | {category} | {reason} |".format(
                    decision=decision["decision"],
                    waiver_id=decision["waiver_id"],
                    requirement_id=decision["requirement_id"] or "-",
                    category=decision["category"],
                    reason=_escape_markdown_table(decision["reason"]),
                )
            )
    return "\n".join(lines) + "\n"


def _raw_hard_gate_findings(
    referenced_ids: list[str],
    packages_by_id: dict[str, dict[str, Any]],
    policy: GatePolicy,
    *,
    changed_paths: list[str] | None = None,
) -> list[dict[str, str | None]]:
    if not referenced_ids:
        return [
            _finding(
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
                _finding(_validation_category(message), requirement_id, path, message)
            )

        status = package["status"]
        allowed_statuses = {status.value for status in policy.rules.allowed_statuses}
        # DEFAULT-DENY MACHINE-PIN GATE (three-zone scope §6; AC4): a machine-pinned status
        # (``MACHINE_PINNED_PENDING_REVIEW``) is accepted ONLY per-path — every changed path on
        # the explicit low-risk allow-list and none on the block-list. It is never in
        # ``allowed_statuses`` (globally), so without the per-path acceptance it is flagged as a
        # status finding (the safe default). ``_machine_pin_accepts`` returns False for any other
        # status, so non-machine statuses are unaffected (AC1 byte-identity for the default path).
        machine_pin_accepted = _machine_pin_accepts(status, changed_paths or [], policy)
        if status is None:
            findings.append(
                _finding(
                    "status",
                    requirement_id,
                    path,
                    "referenced package has no status",
                )
            )
        elif status not in allowed_statuses and not machine_pin_accepted:
            findings.append(
                _finding(
                    "status",
                    requirement_id,
                    path,
                    f"referenced package status is {status}",
                )
            )

        review = package["review"]
        # CATEGORY-2 REVIEW CHECK (ADR 0206 §2; AC1 baseline): a package satisfies the review
        # requirement when its review decision is ``approved`` (the default/human path — AC1
        # byte-identity) OR when it is a machine-pinned package ACCEPTED by the per-path
        # default-deny gate (the machine pin replaces human review for low-risk paths only). A
        # machine-pinned package carries a ``needs_review`` review; without the per-path acceptance
        # it is flagged here (and by the status check above) — a machine pin never fakes human
        # approval. The fabricated package-builder approval (``review_origin="package_builder``,
        # ``decision="approved"``) still satisfies the default path (AC1): this gate site keeps
        # ``decision == "approved"`` (NOT ``is_real_human_review``) because tightening it would
        # block every default package — a direct AC1 violation. The human/non-human distinction
        # for MACHINE pins is enforced at the load-bearing provenance axis
        # (``validate_package`` refuses a machine-pinned package with an ``approved`` review; the
        # ``human_review`` pin backing guard requires ``review_origin="human"``), not here.
        if (
            policy.rules.require_approved_review
            and review["decision"] != "approved"
            and not machine_pin_accepted
        ):
            findings.append(
                _finding(
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
                    "pending_reviews",
                    requirement_id,
                    path,
                    "pending reviews: " + ", ".join(evidence["pending_reviews"]),
                )
            )
        if evidence["unsupported_claims"]:
            findings.append(
                _finding(
                    "unsupported_claims",
                    requirement_id,
                    path,
                    "unsupported claims: " + ", ".join(evidence["unsupported_claims"]),
                )
            )
        missing_evidence = _missing_required_evidence(package, policy.rules.minimum_evidence)
        if missing_evidence:
            findings.append(
                _finding(
                    "minimum_evidence",
                    requirement_id,
                    path,
                    "missing required evidence levels: " + ", ".join(missing_evidence),
                )
            )
    return findings


def _evaluate_finding(
    finding: dict[str, str | None],
    *,
    package: dict[str, Any] | None,
    packages_dir: Path,
    policy: GatePolicy,
    waivers: list[GateWaiver],
    changed_paths: list[str],
    now: datetime,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    evaluated: dict[str, Any] = {
        **finding,
        "scope": "in_scope",
        "enforcement": "report_only",
        "severity": "report_only",
    }
    if not _finding_matches_scope(
        finding,
        package=package,
        packages_dir=packages_dir,
        policy=policy,
        changed_paths=changed_paths,
    ):
        evaluated["scope"] = "out_of_scope"
        evaluated["enforcement"] = "out_of_scope"
        return evaluated, []

    if not _finding_blocks(policy, str(finding["category"])):
        evaluated["enforcement"] = "report_only"
        return evaluated, []

    waived, waiver_id, decisions = _waiver_result(
        finding, package=package, policy=policy, waivers=waivers, now=now
    )
    if waived:
        evaluated["enforcement"] = "waived"
        evaluated["severity"] = "waived"
        evaluated["waiver_id"] = waiver_id
        return evaluated, decisions

    evaluated["enforcement"] = "blocking"
    evaluated["severity"] = "blocker"
    return evaluated, decisions


def _finding_matches_scope(
    finding: dict[str, str | None],
    *,
    package: dict[str, Any] | None,
    packages_dir: Path,
    policy: GatePolicy,
    changed_paths: list[str],
) -> bool:
    scope = policy.scope
    requirement_id = finding["requirement_id"]
    if scope.requirement_id_patterns and requirement_id is not None:
        if not _matches_any(requirement_id, scope.requirement_id_patterns):
            return False

    if scope.adapters and package is not None and package["adapter"] not in scope.adapters:
        return False

    if scope.package_roots:
        path = str(package["path"]) if package is not None else _normalize_path(packages_dir)
        if not any(_path_within_root(path, root) for root in scope.package_roots):
            return False

    if scope.changed_path_patterns and changed_paths:
        return any(_matches_any(path, scope.changed_path_patterns) for path in changed_paths)

    return True


def _finding_blocks(policy: GatePolicy, category: str) -> bool:
    if category in policy.rules.report_only_findings:
        return False
    if category == "minimum_evidence" and policy.rules.minimum_evidence:
        return True
    return category in policy.rules.block_findings


def _waiver_result(
    finding: dict[str, str | None],
    *,
    package: dict[str, Any] | None,
    policy: GatePolicy,
    waivers: list[GateWaiver],
    now: datetime,
) -> tuple[bool, str | None, list[dict[str, Any]]]:
    decisions: list[dict[str, Any]] = []
    for waiver in waivers:
        if not _waiver_covers(waiver, finding, package):
            continue
        decision, reason = _waiver_decision(waiver, package=package, policy=policy, now=now)
        decisions.append(
            {
                "waiver_id": waiver.waiver_id,
                "requirement_id": finding["requirement_id"],
                "path": finding["path"],
                "category": finding["category"],
                "decision": decision,
                "reason": reason,
            }
        )
        if decision == "applied":
            return True, waiver.waiver_id, decisions
    return False, None, decisions


def _waiver_decision(
    waiver: GateWaiver,
    *,
    package: dict[str, Any] | None,
    policy: GatePolicy,
    now: datetime,
) -> tuple[str, str]:
    if not policy.waivers.allow_waivers:
        return "not_allowed", "policy does not allow hard-gate waivers"
    if not waiver.may_satisfy_hard_gate:
        return "not_allowed", "waiver may not satisfy hard-gate enforcement"
    if _as_utc(waiver.expires_at) <= now:
        return "expired", "waiver is expired"
    if policy.waivers.max_duration_days is not None:
        max_expires_at = now + timedelta(days=policy.waivers.max_duration_days)
        if _as_utc(waiver.expires_at) > max_expires_at:
            return "duration_exceeds_policy", "waiver expiration exceeds policy maximum"
    if policy.waivers.require_reviewed_hashes:
        if package is None:
            return "stale", "waiver cannot verify reviewed hashes without a package"
        stale_hashes = _stale_waiver_hashes(waiver, package)
        if stale_hashes:
            return "stale", "reviewed hashes do not match: " + ", ".join(stale_hashes)
    return "applied", "waiver covers this finding"


def _waiver_covers(
    waiver: GateWaiver,
    finding: dict[str, str | None],
    package: dict[str, Any] | None,
) -> bool:
    requirement_id = finding["requirement_id"]
    if requirement_id is not None and requirement_id in waiver.requirement_ids:
        return True
    package_path = package["path"] if package is not None else finding["path"]
    return bool(
        package_path and any(_path_within_root(package_path, path) for path in waiver.package_paths)
    )


def _stale_waiver_hashes(waiver: GateWaiver, package: dict[str, Any]) -> list[str]:
    if not waiver.reviewed_hashes:
        return ["reviewed_hashes"]
    stale: list[str] = []
    package_hashes = package["artifacts"]
    for key, expected_hash in waiver.reviewed_hashes.items():
        artifact = ARTIFACT_HASH_ALIASES.get(key, key)
        if package_hashes.get(artifact) != expected_hash:
            stale.append(key)
    return stale


def _machine_pin_accepts(
    status: object,
    changed_paths: list[str],
    policy: GatePolicy,
) -> bool:
    """Whether a machine-pinned status is ACCEPTED by the default-deny per-path gate (scope §6).

    Returns True ONLY when ALL of:
      * ``status`` is ``MACHINE_PINNED_PENDING_REVIEW`` (any other status → False, so the default
        path and human-accepted statuses are unaffected — AC1 byte-identity);
      * the policy's ``machine_pin`` section is ``enabled``;
      * there is at least one changed path (default-deny: an empty change set has no paths to
        validate against the allow-list, so nothing is accepted);
      * EVERY changed path matches at least one ``allowed_changed_path_patterns`` pattern; AND
      * NO changed path matches any ``block_changed_path_patterns`` pattern (deny wins).

    Unmatched paths, mixed-risk changes, and every auth/funds path therefore require a human
    ``REVIEWED`` package — a machine pin never satisfies them (AC4). Evidence-level requirements
    are NOT waived here (the ``minimum_evidence`` check still runs on an accepted machine-pinned
    package): machine pinning records who pinned the meaning, never a deterministic proof level.
    """
    from .status import is_human_accepted

    # Any non-machine status is unaffected (AC1): the per-path gate is scoped to the machine pin.
    if is_human_accepted(status) or status is None:
        return False
    is_machine = (
        (isinstance(status, FinalStatus) and status is FinalStatus.MACHINE_PINNED_PENDING_REVIEW)
        or (
            isinstance(status, str)
            and status == FinalStatus.MACHINE_PINNED_PENDING_REVIEW.value
        )
    )
    if not is_machine:
        return False
    rules = policy.machine_pin
    if not rules.enabled:
        return False
    if not changed_paths:
        # Default-deny: no changed paths to validate against the allow-list → reject.
        return False
    for path in changed_paths:
        normalized = _normalize_path(path)
        if _matches_any(normalized, rules.block_changed_path_patterns):
            return False
        if not any(fnmatchcase(normalized, _normalize_path(pattern)) for pattern in rules.allowed_changed_path_patterns):
            return False
    return True


def _missing_required_evidence(
    package: dict[str, Any], required_levels: list[EvidenceLevel]
) -> list[str]:
    required = {level.value for level in required_levels}
    if not required:
        return []
    achieved = {
        claim["achieved_evidence"]
        for claim in package["evidence"]["claims"]
        if claim["achieved_evidence"]
    }
    return sorted(required - achieved)


def _finding(
    category: str,
    requirement_id: str | None,
    path: str,
    message: str,
) -> dict[str, str | None]:
    return {
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


def _path_within_root(path: str, root: str) -> bool:
    normalized_path = _normalize_path(path)
    normalized_root = _normalize_path(root).rstrip("/")
    return normalized_path == normalized_root or normalized_path.startswith(normalized_root + "/")


def _matches_any(value: str, patterns: list[str]) -> bool:
    normalized = _normalize_path(value)
    return any(fnmatchcase(normalized, _normalize_path(pattern)) for pattern in patterns)


def _normalize_path(path: str | Path) -> str:
    return Path(path).as_posix()


def _as_utc(value: datetime) -> datetime:
    return value.astimezone(timezone.utc)


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
