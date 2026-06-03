from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .ci_pr_gate import ExtendedCiPrGateReport
from .gate import GatePolicy, GateWaiver
from .jsonutil import sha256_json


POLICY_GOVERNANCE_SCHEMA_VERSION = "0.1"
POLICY_GOVERNANCE_V2_SCHEMA_VERSION = "0.2"
POLICY_GOVERNANCE_TOOL_VERSION = "0.1"


class WaiverAuditFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    waiver_id: str
    status: Literal["active", "expired", "unsafe", "out_of_policy"]
    blocking: bool
    reason: str


class WaiverAuditReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = POLICY_GOVERNANCE_SCHEMA_VERSION
    policy_id: str
    result: Literal["passed", "blocked"]
    findings: list[WaiverAuditFinding] = Field(default_factory=list)
    tool: str = "nlreq.policy_governance"
    tool_version: str = POLICY_GOVERNANCE_TOOL_VERSION


class PolicyChangeRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    change_id: str
    policy_hash: str
    previous_policy_hash: str | None = None
    reviewed_by: str | None = None
    reviewed_at: str | None = None
    rationale: str


class CiPolicyGovernanceReportV2(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.2"] = POLICY_GOVERNANCE_V2_SCHEMA_VERSION
    governance_id: str
    result: Literal["passed", "blocked"]
    ci_report_hash: str
    waiver_audit_hash: str
    required_check_name: str
    branch_protection_required_checks: list[str] = Field(default_factory=list)
    policy_changes: list[PolicyChangeRecord] = Field(default_factory=list)
    unreviewed_policy_changes: list[str] = Field(default_factory=list)
    findings: list[str] = Field(default_factory=list)
    input_hashes: dict[str, str] = Field(default_factory=dict)
    tool: str = "nlreq.policy_governance"
    tool_version: str = POLICY_GOVERNANCE_TOOL_VERSION


def build_waiver_audit_report(
    *,
    policy: GatePolicy,
    waivers: list[GateWaiver],
    now: datetime | None = None,
) -> WaiverAuditReport:
    active_now = now or datetime.now(timezone.utc)
    findings: list[WaiverAuditFinding] = []
    for waiver in waivers:
        if waiver.expires_at <= active_now:
            findings.append(
                WaiverAuditFinding(
                    waiver_id=waiver.waiver_id,
                    status="expired",
                    blocking=True,
                    reason="waiver is expired",
                )
            )
        elif not policy.waivers.allow_waivers:
            findings.append(
                WaiverAuditFinding(
                    waiver_id=waiver.waiver_id,
                    status="out_of_policy",
                    blocking=True,
                    reason="policy does not allow waivers",
                )
            )
        elif (
            policy.waivers.max_duration_days is not None
            and waiver.expires_at > active_now + timedelta(days=policy.waivers.max_duration_days)
        ):
            findings.append(
                WaiverAuditFinding(
                    waiver_id=waiver.waiver_id,
                    status="out_of_policy",
                    blocking=True,
                    reason="waiver expiration exceeds policy maximum duration",
                )
            )
        elif policy.waivers.require_reviewed_hashes and not waiver.reviewed_hashes:
            findings.append(
                WaiverAuditFinding(
                    waiver_id=waiver.waiver_id,
                    status="out_of_policy",
                    blocking=True,
                    reason="policy requires reviewed hashes for waivers",
                )
            )
        elif not waiver.may_satisfy_hard_gate:
            findings.append(
                WaiverAuditFinding(
                    waiver_id=waiver.waiver_id,
                    status="unsafe",
                    blocking=True,
                    reason="waiver may not satisfy hard gate",
                )
            )
        else:
            findings.append(
                WaiverAuditFinding(
                    waiver_id=waiver.waiver_id,
                    status="active",
                    blocking=False,
                    reason="waiver is active and policy allows waivers",
                )
            )
    return WaiverAuditReport(
        policy_id=policy.policy_id,
        result="blocked" if any(finding.blocking for finding in findings) else "passed",
        findings=findings,
    )


def build_ci_policy_governance_report(
    *,
    governance_id: str,
    ci: ExtendedCiPrGateReport,
    waiver_audit: WaiverAuditReport,
    branch_protection_required_checks: list[str],
    policy_changes: list[PolicyChangeRecord],
    required_check_name: str = "nlreq-real-evidence",
    require_reviewed_policy_changes: bool = True,
) -> CiPolicyGovernanceReportV2:
    findings: list[str] = []
    if required_check_name not in branch_protection_required_checks:
        findings.append(f"branch protection is missing required check {required_check_name}")
    if ci.mode != "hard_gate":
        findings.append("CI report is not in hard_gate mode")
    if ci.enforcement != "blocking":
        findings.append("CI enforcement is not blocking")
    if ci.result != "passed":
        findings.append(f"CI result is {ci.result}")
    if not ci.stable_json_hash:
        findings.append("CI stable JSON hash is missing")
    if waiver_audit.result != "passed":
        findings.append("waiver audit did not pass")
    audited_waiver_ids = {finding.waiver_id for finding in waiver_audit.findings}
    missing_waiver_audits = sorted(set(ci.waiver_ids) - audited_waiver_ids)
    if missing_waiver_audits:
        findings.append("CI waivers missing audit entries: " + ", ".join(missing_waiver_audits))
    unreviewed = sorted(
        change.change_id
        for change in policy_changes
        if require_reviewed_policy_changes and (not change.reviewed_by or not change.reviewed_at)
    )
    if unreviewed:
        findings.append("policy changes missing review: " + ", ".join(unreviewed))
    return CiPolicyGovernanceReportV2(
        governance_id=governance_id,
        result="blocked" if findings else "passed",
        ci_report_hash=sha256_json(ci),
        waiver_audit_hash=sha256_json(waiver_audit),
        required_check_name=required_check_name,
        branch_protection_required_checks=branch_protection_required_checks,
        policy_changes=policy_changes,
        unreviewed_policy_changes=unreviewed,
        findings=findings,
        input_hashes={
            "ci": sha256_json(ci),
            "waiver_audit": sha256_json(waiver_audit),
            "branch_protection_required_checks": sha256_json(branch_protection_required_checks),
            "policy_changes": sha256_json(policy_changes),
        },
    )
